from rest_framework import serializers

from common.serializer import (
    AttachmentsSerializer,
    LeadCommentSerializer,
    ProfileSerializer,
    TagsSerializer,
    TeamsSerializer,
    UserSerializer,
)
from common.utils import LEAD_STATUS
from contacts.serializer import ContactSerializer
from leads.models import Lead, LeadInteraction, LeadPipeline, LeadStage
from leads.outcomes import get_active_outcome_values


class LeadSerializer(serializers.ModelSerializer):
    contacts = ContactSerializer(read_only=True, many=True)
    assigned_to = ProfileSerializer(read_only=True, many=True)
    created_by = UserSerializer()
    tags = TagsSerializer(read_only=True, many=True)
    lead_attachment = AttachmentsSerializer(read_only=True, many=True)
    teams = TeamsSerializer(read_only=True, many=True)
    lead_comments = LeadCommentSerializer(read_only=True, many=True)

    class Meta:
        model = Lead
        fields = (
            "id",
            # Core Lead Information
            "title",
            "salutation",
            "first_name",
            "last_name",
            "email",
            "phone",
            "job_title",
            "website",
            "linkedin_url",
            # Sales Pipeline
            "status",
            "source",
            "industry",
            "rating",
            "opportunity_amount",
            "currency",
            "probability",
            "close_date",
            # Address
            "address_line",
            "city",
            "state",
            "postcode",
            "country",
            # Assignment
            "assigned_to",
            "teams",
            # Activity
            "last_contacted",
            "next_follow_up",
            "description",
            # Related
            "contacts",
            "lead_attachment",
            "lead_comments",
            "tags",
            # System
            "created_by",
            "created_at",
            "updated_at",
            "is_active",
            "company_name",
            # Kanban
            "stage",
            "kanban_order",
            # Per-org custom fields (validated via common.custom_fields)
            "custom_fields",
        )


class LeadCreateSerializer(serializers.ModelSerializer):
    probability = serializers.IntegerField(
        max_value=100, required=False, allow_null=True
    )
    opportunity_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    close_date = serializers.DateField(required=False, allow_null=True)

    def __init__(self, *args, **kwargs):
        request_obj = kwargs.pop("request_obj", None)
        super().__init__(*args, **kwargs)
        if self.initial_data and self.initial_data.get("status") == "converted":
            self.fields["email"].required = True
        self.fields["first_name"].required = False
        self.fields["last_name"].required = False
        self.fields["salutation"].required = False
        self.org = request_obj.profile.org

    class Meta:
        model = Lead
        fields = (
            # Core Lead Information
            "title",
            "salutation",
            "first_name",
            "last_name",
            "email",
            "phone",
            "job_title",
            "website",
            "linkedin_url",
            # Sales Pipeline
            "status",
            "source",
            "industry",
            "rating",
            "opportunity_amount",
            "currency",
            "probability",
            "close_date",
            # Address
            "address_line",
            "city",
            "state",
            "postcode",
            "country",
            # Activity
            "last_contacted",
            "next_follow_up",
            "description",
            # System
            "company_name",
            "is_active",
        )

    def create(self, validated_data):
        # Default currency from org if not provided and has opportunity_amount
        if not validated_data.get("currency") and validated_data.get(
            "opportunity_amount"
        ):
            request = self.context.get("request")
            if request and hasattr(request, "profile") and request.profile.org:
                validated_data["currency"] = request.profile.org.default_currency
        return super().create(validated_data)


class LeadCreateSwaggerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = [
            # Core Lead Information
            "title",
            "salutation",
            "first_name",
            "last_name",
            "email",
            "phone",
            "job_title",
            "website",
            "linkedin_url",
            # Sales Pipeline
            "status",
            "source",
            "industry",
            "rating",
            "opportunity_amount",
            "probability",
            "close_date",
            # Address
            "address_line",
            "city",
            "state",
            "postcode",
            "country",
            # Assignment & Related
            "assigned_to",
            "teams",
            "contacts",
            "tags",
            # Activity
            "last_contacted",
            "next_follow_up",
            "description",
            # System
            "company_name",
        ]


class CreateLeadFromSiteSwaggerSerializer(serializers.Serializer):
    apikey = serializers.CharField()
    title = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    phone = serializers.CharField()
    email = serializers.CharField()
    source = serializers.CharField()
    description = serializers.CharField()


class LeadDetailEditSwaggerSerializer(serializers.Serializer):
    comment = serializers.CharField()
    lead_attachment = serializers.FileField()


class LeadCommentEditSwaggerSerializer(serializers.Serializer):
    comment = serializers.CharField()


class LeadUploadSwaggerSerializer(serializers.Serializer):
    leads_file = serializers.FileField()


# ============================================
# Kanban Serializers
# ============================================


class LeadStageSerializer(serializers.ModelSerializer):
    """Serializer for lead stages."""

    lead_count = serializers.SerializerMethodField()

    class Meta:
        model = LeadStage
        fields = [
            "id",
            "name",
            "order",
            "color",
            "stage_type",
            "maps_to_status",
            "win_probability",
            "wip_limit",
            "lead_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("id", "created_at", "updated_at", "org")

    def get_lead_count(self, obj):
        return obj.leads.count()


class LeadPipelineSerializer(serializers.ModelSerializer):
    """Serializer for lead pipelines with nested stages."""

    stages = LeadStageSerializer(many=True, read_only=True)
    stage_count = serializers.SerializerMethodField()
    lead_count = serializers.SerializerMethodField()

    class Meta:
        model = LeadPipeline
        fields = [
            "id",
            "name",
            "description",
            "is_default",
            "is_active",
            "stages",
            "stage_count",
            "lead_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("id", "created_at", "updated_at", "org")

    def get_stage_count(self, obj):
        return obj.stages.count()

    def get_lead_count(self, obj):
        return Lead.objects.filter(stage__pipeline=obj).count()


class LeadPipelineListSerializer(serializers.ModelSerializer):
    """Simplified pipeline serializer for lists."""

    stage_count = serializers.SerializerMethodField()
    lead_count = serializers.SerializerMethodField()

    class Meta:
        model = LeadPipeline
        fields = [
            "id",
            "name",
            "description",
            "is_default",
            "is_active",
            "stage_count",
            "lead_count",
            "created_at",
        ]

    def get_stage_count(self, obj):
        return obj.stages.count()

    def get_lead_count(self, obj):
        return Lead.objects.filter(stage__pipeline=obj).count()


class LeadKanbanCardSerializer(serializers.ModelSerializer):
    """Lightweight serializer for kanban cards (minimal fields for performance)."""

    assigned_to = ProfileSerializer(read_only=True, many=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = Lead
        fields = [
            "id",
            "title",
            "full_name",
            "company_name",
            "email",
            "rating",
            "opportunity_amount",
            "currency",
            "status",
            "stage",
            "kanban_order",
            "next_follow_up",
            "is_follow_up_overdue",
            "assigned_to",
            "created_at",
        ]

    def get_full_name(self, obj):
        return str(obj)


class LeadMoveSerializer(serializers.Serializer):
    """Serializer for moving leads in kanban."""

    stage_id = serializers.UUIDField(required=False, allow_null=True)
    status = serializers.ChoiceField(choices=LEAD_STATUS, required=False)
    kanban_order = serializers.DecimalField(
        max_digits=15, decimal_places=6, required=False
    )
    above_lead_id = serializers.UUIDField(required=False, allow_null=True)
    below_lead_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs):
        # Must provide either stage_id or status
        if not attrs.get("stage_id") and not attrs.get("status"):
            raise serializers.ValidationError(
                "Either stage_id or status must be provided"
            )
        return attrs


class LeadInteractionSerializer(serializers.ModelSerializer):
    """A single logged contact (timeline row) on a lead.

    `outcome` is validated against the org's admin-managed option list. `org`
    and `lead` are set by the view, not the client.
    """

    created_by = UserSerializer(read_only=True)
    interaction_type_display = serializers.CharField(
        source="get_interaction_type_display", read_only=True
    )

    class Meta:
        model = LeadInteraction
        fields = [
            "id",
            "lead",
            "interaction_type",
            "interaction_type_display",
            "outcome",
            "notes",
            "occurred_at",
            "next_follow_up",
            "created_by",
            "created_at",
        ]
        read_only_fields = ("id", "lead", "created_by", "created_at")

    def validate_notes(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Notes are required.")
        return value.strip()

    def validate_outcome(self, value):
        if not value:
            return value
        org = self.context.get("org")
        allowed = get_active_outcome_values(org) if org else set()
        # Only enforce membership when the org has configured an outcome list.
        if allowed and value not in allowed:
            raise serializers.ValidationError(
                f"must be one of {sorted(allowed)}"
            )
        return value
