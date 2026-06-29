from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.models import APISettings, Attachments, Comment
from common.permissions import HasOrgContext
from common.serializer import LeadCommentSerializer
from contacts.models import Contact
from leads import swagger_params
from leads.forms import LeadListForm
from leads.models import Lead, LeadInteraction
from leads.serializer import (
    CreateLeadFromSiteSwaggerSerializer,
    LeadCommentEditSwaggerSerializer,
    LeadInteractionSerializer,
    LeadUploadSwaggerSerializer,
)
from leads.tasks import create_lead_from_file, send_lead_assigned_emails
from tasks.models import Task


class LeadUploadView(APIView):
    model = Lead
    permission_classes = (IsAuthenticated, HasOrgContext)

    @extend_schema(
        tags=["Leads"],
        parameters=swagger_params.organization_params,
        request=LeadUploadSwaggerSerializer,
        responses={
            200: inline_serializer(
                name="LeadUploadResponse",
                fields={
                    "error": serializers.BooleanField(),
                    "message": serializers.CharField(),
                },
            )
        },
    )
    def post(self, request, *args, **kwargs):
        lead_form = LeadListForm(request.POST, request.FILES)
        if lead_form.is_valid():
            create_lead_from_file.delay(
                lead_form.validated_rows,
                lead_form.invalid_rows,
                request.profile.id,
                request.get_host(),
                request.profile.org.id,
            )
            return Response(
                {"error": False, "message": "Leads created Successfully"},
                status=status.HTTP_200_OK,
            )
        return Response(
            {"error": True, "errors": lead_form.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


class LeadCommentView(APIView):
    model = Comment
    permission_classes = (IsAuthenticated, HasOrgContext)

    def get_object(self, pk):
        return self.model.objects.get(pk=pk, org=self.request.profile.org)

    @extend_schema(
        tags=["Leads"],
        parameters=swagger_params.organization_params,
        request=LeadCommentEditSwaggerSerializer,
        responses={
            200: inline_serializer(
                name="LeadCommentUpdateResponse",
                fields={
                    "error": serializers.BooleanField(),
                    "message": serializers.CharField(),
                },
            )
        },
    )
    def put(self, request, pk, format=None):
        params = request.data
        obj = self.get_object(pk)
        if (
            request.profile.role == "ADMIN"
            or request.user.is_superuser
            or request.profile == obj.commented_by
        ):
            serializer = LeadCommentSerializer(obj, data=params)
            if serializer.is_valid():
                serializer.save()
                return Response(
                    {"error": False, "message": "Comment Submitted"},
                    status=status.HTTP_200_OK,
                )
            return Response(
                {"error": True, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "error": True,
                "errors": "You don't have permission to perform this action",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    @extend_schema(
        tags=["Leads"],
        parameters=swagger_params.organization_params,
        request=LeadCommentEditSwaggerSerializer,
        description="Partial Comment Update",
        responses={
            200: inline_serializer(
                name="LeadCommentPatchResponse",
                fields={
                    "error": serializers.BooleanField(),
                    "message": serializers.CharField(),
                },
            )
        },
    )
    def patch(self, request, pk, format=None):
        """Handle partial updates to a comment."""
        params = request.data
        obj = self.get_object(pk)
        if (
            request.profile.role == "ADMIN"
            or request.user.is_superuser
            or request.profile == obj.commented_by
        ):
            serializer = LeadCommentSerializer(obj, data=params, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(
                    {"error": False, "message": "Comment Updated"},
                    status=status.HTTP_200_OK,
                )
            return Response(
                {"error": True, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "error": True,
                "errors": "You don't have permission to perform this action",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    @extend_schema(
        tags=["Leads"],
        parameters=swagger_params.organization_params,
        responses={
            200: inline_serializer(
                name="LeadCommentDeleteResponse",
                fields={
                    "error": serializers.BooleanField(),
                    "message": serializers.CharField(),
                },
            )
        },
    )
    def delete(self, request, pk, format=None):
        self.object = self.get_object(pk)
        if (
            request.profile.role == "ADMIN"
            or request.user.is_superuser
            or request.profile == self.object.commented_by
        ):
            self.object.delete()
            return Response(
                {"error": False, "message": "Comment Deleted Successfully"},
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "error": True,
                "errors": "You do not have permission to perform this action",
            },
            status=status.HTTP_403_FORBIDDEN,
        )


class LeadAttachmentView(APIView):
    model = Attachments
    permission_classes = (IsAuthenticated, HasOrgContext)

    @extend_schema(
        tags=["Leads"],
        parameters=swagger_params.organization_params,
        responses={
            200: inline_serializer(
                name="LeadAttachmentDeleteResponse",
                fields={
                    "error": serializers.BooleanField(),
                    "message": serializers.CharField(),
                },
            )
        },
    )
    def delete(self, request, pk, format=None):
        self.object = self.model.objects.get(pk=pk)
        if (
            request.profile.role == "ADMIN"
            or request.user.is_superuser
            or request.profile.user == self.object.created_by
        ):
            self.object.delete()
            return Response(
                {"error": False, "message": "Attachment Deleted Successfully"},
                status=status.HTTP_200_OK,
            )
        return Response(
            {
                "error": True,
                "errors": "You don't have permission to perform this action",
            },
            status=status.HTTP_403_FORBIDDEN,
        )


class CreateLeadFromSite(APIView):
    @extend_schema(
        tags=["Leads"],
        parameters=swagger_params.organization_params,
        request=CreateLeadFromSiteSwaggerSerializer,
        responses={
            200: inline_serializer(
                name="CreateLeadFromSiteResponse",
                fields={
                    "error": serializers.BooleanField(),
                    "message": serializers.CharField(),
                },
            )
        },
    )
    def post(self, request, *args, **kwargs):
        params = request.data
        api_key = params.get("apikey")
        # api_setting = APISettings.objects.filter(
        #     website=website_address, apikey=api_key).first()
        api_setting = APISettings.objects.filter(apikey=api_key).first()
        if not api_setting:
            return Response(
                {
                    "error": True,
                    "message": "You don't have permission, please contact the admin!.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if api_setting and params.get("email"):
            # user = User.objects.filter(is_admin=True, is_active=True).first()
            user = api_setting.created_by
            lead = Lead.objects.create(
                salutation=params.get(
                    "title"
                ),  # 'title' param maps to salutation for backwards compatibility
                first_name=params.get("first_name"),
                last_name=params.get("last_name"),
                status="assigned",
                source=api_setting.website,
                description=params.get("message"),
                email=params.get("email"),
                phone=params.get("phone"),
                is_active=True,
                created_by=user,
                org=api_setting.org,
            )
            lead.assigned_to.add(user)
            # Send Email to Assigned Users
            site_address = request.scheme + "://" + request.META["HTTP_HOST"]
            send_lead_assigned_emails.delay(
                lead.id, [user.id], site_address, str(api_setting.org.id)
            )
            # Create Contact
            try:
                contact = Contact.objects.create(
                    first_name=params.get("first_name") or "",
                    last_name=params.get("last_name") or "",
                    email=params.get("email"),
                    phone=params.get("phone"),
                    description=params.get("message"),
                    created_by=user,
                    is_active=True,
                    org=api_setting.org,
                )
                contact.assigned_to.add(user)

                lead.contacts.add(contact)
            except Exception:
                pass

            return Response(
                {"error": False, "message": "Lead Created sucessfully."},
                status=status.HTTP_200_OK,
            )
        return Response(
            {"error": True, "message": "Invalid data"},
            status=status.HTTP_400_BAD_REQUEST,
        )


def _sync_followup_task(lead, interaction, profile):
    """Mirror a logged follow-up into a CRM Task so it shows in "My Tasks" /
    "Due Today".

    Keeps a single rolling follow-up task per lead (tagged via custom_fields):
    a later logged contact reschedules the same task instead of piling up. The
    task is assigned to the lead's current assignees, falling back to the rep
    who logged the contact.
    """
    if not interaction.next_follow_up:
        return

    task = (
        Task.objects.filter(
            lead=lead,
            org=lead.org,
            status__in=["New", "In Progress"],
            custom_fields___auto_followup=True,
        )
        .order_by("-created_at")
        .first()
    )
    if task is None:
        task = Task(
            title=f"Follow up: {lead}",
            status="New",
            priority="Medium",
            lead=lead,
            org=lead.org,
            custom_fields={"_auto_followup": True},
        )
    task.due_date = interaction.next_follow_up
    if interaction.notes:
        task.description = interaction.notes
    task.save()

    assignees = list(lead.assigned_to.all())
    if not assignees and profile is not None:
        assignees = [profile]
    if assignees:
        task.assigned_to.set(assignees)


class LeadInteractionListCreateView(APIView):
    """GET timeline of interactions for a lead; POST logs a new contact.

    Logging a contact stamps the lead's ``last_contacted`` (removing it from
    the dashboard "New Leads to Contact" banner) and advances
    ``next_follow_up`` when one is supplied.
    """

    permission_classes = (IsAuthenticated, HasOrgContext)

    def _get_lead(self, pk, org):
        return Lead.objects.filter(pk=pk, org=org).first()

    @extend_schema(
        tags=["Leads"],
        responses={200: LeadInteractionSerializer(many=True)},
    )
    def get(self, request, pk, *args, **kwargs):
        lead = self._get_lead(pk, request.profile.org)
        if not lead:
            return Response(
                {"error": True, "errors": "Lead not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        interactions = lead.interactions.all().order_by("-occurred_at")
        return Response(
            {"interactions": LeadInteractionSerializer(interactions, many=True).data}
        )

    @extend_schema(
        tags=["Leads"],
        request=LeadInteractionSerializer,
        responses={201: LeadInteractionSerializer},
    )
    def post(self, request, pk, *args, **kwargs):
        org = request.profile.org
        lead = self._get_lead(pk, org)
        if not lead:
            return Response(
                {"error": True, "errors": "Lead not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = LeadInteractionSerializer(
            data=request.data, context={"org": org}
        )
        if not serializer.is_valid():
            return Response(
                {"error": True, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        interaction = serializer.save(
            lead=lead, org=org, created_by=request.profile.user
        )

        # Keep the lead in sync: mark contacted (drops it from the "New Leads to
        # Contact" banner) and advance the next follow-up if one was set.
        update_fields = ["last_contacted"]
        lead.last_contacted = interaction.occurred_at.date()
        if interaction.next_follow_up:
            lead.next_follow_up = interaction.next_follow_up
            update_fields.append("next_follow_up")
        lead.save(update_fields=update_fields)

        # Surface the follow-up as a task in "My Tasks" / "Due Today".
        _sync_followup_task(lead, interaction, request.profile)

        return Response(
            LeadInteractionSerializer(interaction).data,
            status=status.HTTP_201_CREATED,
        )


class LeadInteractionDetailView(APIView):
    """PATCH / DELETE a single interaction (author or admin only)."""

    permission_classes = (IsAuthenticated, HasOrgContext)

    def _get_object(self, pk, org):
        return LeadInteraction.objects.filter(pk=pk, org=org).first()

    def _can_edit(self, request, obj):
        return (
            request.profile.role == "ADMIN"
            or request.user.is_superuser
            or obj.created_by == request.profile.user
        )

    @extend_schema(
        tags=["Leads"],
        request=LeadInteractionSerializer,
        responses={200: LeadInteractionSerializer},
    )
    def patch(self, request, pk, *args, **kwargs):
        obj = self._get_object(pk, request.profile.org)
        if not obj:
            return Response(
                {"error": True, "errors": "Interaction not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not self._can_edit(request, obj):
            return Response(
                {"error": True, "errors": "You don't have permission to edit this."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = LeadInteractionSerializer(
            obj, data=request.data, partial=True, context={"org": request.profile.org}
        )
        if not serializer.is_valid():
            return Response(
                {"error": True, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer.save()
        return Response(serializer.data)

    @extend_schema(
        tags=["Leads"],
        responses={
            200: inline_serializer(
                name="LeadInteractionDeleteResponse",
                fields={
                    "error": serializers.BooleanField(),
                    "message": serializers.CharField(),
                },
            )
        },
    )
    def delete(self, request, pk, *args, **kwargs):
        obj = self._get_object(pk, request.profile.org)
        if not obj:
            return Response(
                {"error": True, "errors": "Interaction not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not self._can_edit(request, obj):
            return Response(
                {"error": True, "errors": "You don't have permission to delete this."},
                status=status.HTTP_403_FORBIDDEN,
            )
        obj.delete()
        return Response(
            {"error": False, "message": "Interaction deleted"},
            status=status.HTTP_200_OK,
        )
