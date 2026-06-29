"""CSV import endpoints for leads.

Preview validates the uploaded file without touching the DB; commit re-runs
validation and writes inside a single transaction. Both are gated to ADMIN or
sales-access users so non-privileged members can't mass-create leads.
"""

import io

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import HasOrgContext
from leads.services.csv_import import (
    TEMPLATE_EXAMPLE,
    TEMPLATE_HEADERS,
    commit_rows,
    parse_and_validate,
)

XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB; matches the UI hint


def _can_import(profile) -> bool:
    if profile is None:
        return False
    if getattr(profile, "role", None) == "ADMIN":
        return True
    if getattr(profile, "is_admin", False):
        return True
    return bool(getattr(profile, "has_sales_access", False))


def _skip_duplicates(request) -> bool:
    raw = str(request.data.get("skip_duplicates", "")).strip().lower()
    return raw in ("1", "true", "yes", "on")


def _read_upload(request):
    upload = request.FILES.get("file")
    if not upload:
        return None, Response(
            {"error": True, "message": "No file uploaded (expected field 'file')"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not (upload.name or "").lower().endswith((".csv", ".xlsx")):
        return None, Response(
            {"error": True, "message": "File must be a .csv or .xlsx"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    file_bytes = upload.read()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        return None, Response(
            {"error": True, "message": "File exceeds the 5 MB upload limit"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return file_bytes, None


class LeadImportTemplateView(APIView):
    """Download a ready-to-fill .xlsx template (headers + one example row)."""

    permission_classes = (IsAuthenticated, HasOrgContext)

    @extend_schema(tags=["Leads"], responses={200: None})
    def get(self, request, *args, **kwargs):
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Leads"
        ws.append(TEMPLATE_HEADERS)
        ws.append(TEMPLATE_EXAMPLE)
        buf = io.BytesIO()
        wb.save(buf)
        response = HttpResponse(buf.getvalue(), content_type=XLSX_CONTENT_TYPE)
        response["Content-Disposition"] = (
            'attachment; filename="leads-import-template.xlsx"'
        )
        return response


class LeadImportPreviewView(APIView):
    permission_classes = (IsAuthenticated, HasOrgContext)
    parser_classes = (MultiPartParser,)

    @extend_schema(
        tags=["Leads"],
        request=inline_serializer(
            name="LeadImportPreviewRequest",
            fields={"file": serializers.FileField()},
        ),
        responses={
            200: inline_serializer(
                name="LeadImportPreviewResponse",
                fields={
                    "header_error": serializers.CharField(allow_null=True),
                    "valid": serializers.ListField(child=serializers.DictField()),
                    "errors": serializers.ListField(child=serializers.DictField()),
                    "summary": serializers.DictField(),
                },
            )
        },
    )
    def post(self, request, *args, **kwargs):
        if not _can_import(request.profile):
            return Response(
                {"error": True, "message": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN,
            )
        file_bytes, err = _read_upload(request)
        if err is not None:
            return err
        result = parse_and_validate(
            file_bytes, request.profile.org, skip_duplicates=_skip_duplicates(request)
        )
        return Response(result.to_dict(), status=status.HTTP_200_OK)


class LeadImportCommitView(APIView):
    permission_classes = (IsAuthenticated, HasOrgContext)
    parser_classes = (MultiPartParser,)

    @extend_schema(
        tags=["Leads"],
        request=inline_serializer(
            name="LeadImportCommitRequest",
            fields={"file": serializers.FileField()},
        ),
        responses={
            200: inline_serializer(
                name="LeadImportCommitResponse",
                fields={
                    "error": serializers.BooleanField(),
                    "created": serializers.IntegerField(),
                    "ids": serializers.ListField(child=serializers.CharField()),
                },
            )
        },
    )
    def post(self, request, *args, **kwargs):
        if not _can_import(request.profile):
            return Response(
                {"error": True, "message": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN,
            )
        file_bytes, err = _read_upload(request)
        if err is not None:
            return err
        result = commit_rows(
            file_bytes,
            request.profile.org,
            request.profile,
            skip_duplicates=_skip_duplicates(request),
        )
        http_status = (
            status.HTTP_400_BAD_REQUEST if result.get("error") else status.HTTP_200_OK
        )
        return Response(result, status=http_status)
