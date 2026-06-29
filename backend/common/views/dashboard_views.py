from datetime import date

from django.db.models import Count, DecimalField, F, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer

from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Account
from accounts.serializer import AccountSerializer
from common import serializer, swagger_params
from common.models import Activity, Profile
from common.permissions import HasOrgContext
from common.utils import STAGES
from contacts.models import Contact
from contacts.serializer import ContactSerializer
from leads.models import Lead, LeadInteraction
from leads.serializer import LeadSerializer
from opportunity.models import Opportunity
from opportunity.serializer import OpportunitySerializer
from tasks.models import Task
from tasks.serializer import TaskSerializer


class ApiHomeView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        tags=["home"],
        parameters=swagger_params.organization_params,
        responses={
            200: inline_serializer(
                name="ApiHomeResponse",
                fields={
                    "accounts_count": serializers.IntegerField(),
                    "contacts_count": serializers.IntegerField(),
                    "leads_count": serializers.IntegerField(),
                    "opportunities_count": serializers.IntegerField(),
                    "accounts": AccountSerializer(many=True),
                    "contacts": ContactSerializer(many=True),
                    "leads": LeadSerializer(many=True),
                    "opportunities": OpportunitySerializer(many=True),
                },
            )
        },
    )
    def get(self, request, format=None):
        org = request.profile.org
        profile = request.profile
        today = date.today()

        accounts = Account.objects.filter(is_active=True, org=org)
        contacts = Contact.objects.filter(org=org)
        leads = Lead.objects.filter(org=org).exclude(
            Q(status="converted") | Q(status="closed")
        )
        opportunities = Opportunity.objects.filter(org=org)
        tasks = Task.objects.filter(org=org)

        is_admin = profile.role == "ADMIN" or request.user.is_superuser

        if not is_admin:
            accounts = accounts.filter(
                Q(assigned_to=profile) | Q(created_by=profile.user)
            )
            contacts = contacts.filter(
                Q(assigned_to__id__in=[profile.id]) | Q(created_by=profile.user)
            )
            leads = leads.filter(
                Q(assigned_to__id__in=[profile.id]) | Q(created_by=profile.user)
            ).exclude(status="closed")
            opportunities = opportunities.filter(
                Q(assigned_to__id__in=[profile.id]) | Q(created_by=profile.user)
            )
            tasks = tasks.filter(
                Q(assigned_to__id__in=[profile.id]) | Q(created_by=profile.user)
            )

        # Build base context (existing)
        context = {}
        context["accounts_count"] = accounts.count()
        context["contacts_count"] = contacts.count()
        context["leads_count"] = leads.count()
        context["opportunities_count"] = opportunities.count()
        context["accounts"] = AccountSerializer(accounts, many=True).data
        context["contacts"] = ContactSerializer(contacts, many=True).data
        context["leads"] = LeadSerializer(leads, many=True).data
        context["opportunities"] = OpportunitySerializer(opportunities, many=True).data

        # NEW: Urgent counts for Focus Bar
        overdue_tasks = tasks.filter(
            status__in=["New", "In Progress"], due_date__lt=today
        ).count()

        tasks_due_today = tasks.filter(
            status__in=["New", "In Progress"], due_date=today
        ).count()

        followups_today = leads.filter(next_follow_up=today).count()

        hot_leads = leads.filter(
            rating="HOT", status__in=["assigned", "in process"]
        ).count()

        # Leads assigned to the current user that have never been contacted —
        # these need a first touch and are surfaced on the dashboard banner.
        new_assigned_leads_qs = (
            Lead.objects.filter(
                org=org, assigned_to=profile, last_contacted__isnull=True
            )
            .exclude(status__in=["converted", "closed"])
            .order_by("-created_at")
        )
        new_leads_count = new_assigned_leads_qs.count()

        context["urgent_counts"] = {
            "overdue_tasks": overdue_tasks,
            "tasks_due_today": tasks_due_today,
            "followups_today": followups_today,
            "hot_leads": hot_leads,
            "new_leads": new_leads_count,
        }

        # Get org's default currency for filtering
        org_currency = org.default_currency or "USD"

        # NEW: Pipeline by stage (filtered by org's default currency)
        # Only sum amounts that match org's currency for accurate totals
        pipeline_by_stage = {}
        for stage_code, stage_label in STAGES:
            stage_opps = opportunities.filter(stage=stage_code)
            # Filter by currency for value calculation (include null as matching org currency)
            stage_opps_with_currency = stage_opps.filter(
                Q(currency=org_currency) | Q(currency__isnull=True) | Q(currency="")
            )
            stage_value = stage_opps_with_currency.aggregate(
                total=Coalesce(Sum("amount"), 0, output_field=DecimalField())
            )["total"]
            pipeline_by_stage[stage_code] = {
                "count": stage_opps.count(),  # Count all opportunities
                "value": float(stage_value or 0),  # Value only for matching currency
                "label": stage_label,
            }
        context["pipeline_by_stage"] = pipeline_by_stage

        # NEW: Revenue metrics (filtered by org's default currency)
        open_stages = ["PROSPECTING", "QUALIFICATION", "PROPOSAL", "NEGOTIATION"]
        open_opps = opportunities.filter(stage__in=open_stages)
        # Filter by currency for value calculations
        open_opps_with_currency = open_opps.filter(
            Q(currency=org_currency) | Q(currency__isnull=True) | Q(currency="")
        )

        pipeline_value = open_opps_with_currency.aggregate(
            total=Coalesce(Sum("amount"), 0, output_field=DecimalField())
        )["total"]

        # Weighted pipeline = sum of (amount * probability / 100)
        weighted_pipeline = open_opps_with_currency.aggregate(
            total=Coalesce(
                Sum(F("amount") * F("probability") / 100),
                0,
                output_field=DecimalField(),
            )
        )["total"]

        # Won this month (use timezone-aware datetime for updated_at comparison)
        now = timezone.now()
        first_day_of_month = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        won_opps = opportunities.filter(
            stage="CLOSED_WON", updated_at__gte=first_day_of_month
        )
        won_opps_with_currency = won_opps.filter(
            Q(currency=org_currency) | Q(currency__isnull=True) | Q(currency="")
        )
        won_this_month = won_opps_with_currency.aggregate(
            total=Coalesce(Sum("amount"), 0, output_field=DecimalField())
        )["total"]

        # Conversion rate: leads converted / total leads
        total_leads_all = Lead.objects.filter(org=org).count()
        converted_leads = Lead.objects.filter(org=org, status="converted").count()
        conversion_rate = (
            (converted_leads / total_leads_all * 100) if total_leads_all > 0 else 0
        )

        # Count opportunities in other currencies (for info)
        other_currency_count = opportunities.exclude(
            Q(currency=org_currency) | Q(currency__isnull=True) | Q(currency="")
        ).count()

        context["revenue_metrics"] = {
            "pipeline_value": float(pipeline_value or 0),
            "weighted_pipeline": float(weighted_pipeline or 0),
            "won_this_month": float(won_this_month or 0),
            "conversion_rate": round(conversion_rate, 1),
            "currency": org_currency,
            "other_currency_count": other_currency_count,
        }

        # NEW: Hot leads list for dedicated panel
        hot_leads_qs = leads.filter(
            rating="HOT", status__in=["assigned", "in process"]
        ).order_by("-created_at")[:10]

        context["hot_leads"] = [
            {
                "id": str(lead.id),
                "first_name": lead.first_name,
                "last_name": lead.last_name,
                "company": lead.company_name,
                "rating": lead.rating,
                "next_follow_up": lead.next_follow_up.isoformat()
                if lead.next_follow_up
                else None,
                "last_contacted": lead.last_contacted.isoformat()
                if lead.last_contacted
                else None,
            }
            for lead in hot_leads_qs
        ]

        # NEW: Newly-assigned, uncontacted leads for the "Contact First" banner
        context["new_assigned_leads"] = [
            {
                "id": str(lead.id),
                "first_name": lead.first_name,
                "last_name": lead.last_name,
                "company": lead.company_name,
                "rating": lead.rating,
                "status": lead.status,
                "phone": lead.phone,
                "email": lead.email,
                "next_follow_up": lead.next_follow_up.isoformat()
                if lead.next_follow_up
                else None,
                "created_at": lead.created_at.isoformat() if lead.created_at else None,
            }
            for lead in new_assigned_leads_qs[:10]
        ]

        # Include tasks in dashboard response (avoid separate API call)
        upcoming_tasks = tasks.filter(
            status__in=["New", "In Progress"], due_date__isnull=False
        ).order_by("due_date")[:10]
        context["tasks"] = TaskSerializer(upcoming_tasks, many=True).data

        # Goal summary for current user
        from opportunity.models import SalesGoal

        goal_filter = Q(assigned_to=profile) | Q(team__in=profile.user_teams.all())
        if is_admin:
            goal_filter |= Q(assigned_to__isnull=True, team__isnull=True)

        active_goals = (
            SalesGoal.objects.filter(
                org=org,
                is_active=True,
                period_start__lte=today,
                period_end__gte=today,
            )
            .filter(goal_filter)
            .distinct()[:3]
        )
        context["goal_summary"] = [
            {
                "id": str(g.id),
                "name": g.name,
                "goal_type": g.goal_type,
                "target_value": float(g.target_value),
                "progress_value": float(g.compute_progress()),
                "progress_percent": g.progress_percent,
                "status": g.status,
            }
            for g in active_goals
        ]

        # Include recent activities (avoid separate API call)
        activities = (
            Activity.objects.filter(org=org)
            .select_related("user", "user__user")
            .order_by("-created_at")[:10]
        )
        context["activities"] = serializer.ActivitySerializer(
            activities, many=True
        ).data

        return Response(context, status=status.HTTP_200_OK)


class ActivityListView(APIView):
    """
    Get recent activities for the organization
    Returns the last 10 activities by default
    """

    permission_classes = (IsAuthenticated,)

    @extend_schema(
        tags=["activities"],
        parameters=swagger_params.organization_params
        + [
            OpenApiParameter(
                name="limit",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Number of activities to return (default: 10, max: 50)",
            ),
            OpenApiParameter(
                name="entity_type",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter by entity type (Account, Lead, Contact, etc.)",
            ),
        ],
        responses={200: serializer.ActivitySerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        if not request.profile:
            return Response(
                {"error": True, "errors": "Organization context required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get query params
        limit = min(int(request.query_params.get("limit", 10)), 50)
        entity_type = request.query_params.get("entity_type", None)

        # Query activities for this organization
        queryset = Activity.objects.filter(org=request.profile.org)

        # Filter by entity type if specified
        if entity_type:
            queryset = queryset.filter(entity_type=entity_type)

        # Get most recent activities
        activities = queryset.select_related("user", "user__user")[:limit]

        # Serialize
        activities_data = serializer.ActivitySerializer(activities, many=True).data

        return Response(
            {
                "error": False,
                "count": len(activities_data),
                "activities": activities_data,
            },
            status=status.HTTP_200_OK,
        )


class AdminDashboardView(APIView):
    """Org-wide overview for admins: lead/assignment health, per-rep metrics,
    and a recent lead-activity feed. Admin (or superuser) only.
    """

    permission_classes = (IsAuthenticated, HasOrgContext)

    @extend_schema(tags=["home"], responses={200: None})
    def get(self, request, format=None):
        profile = request.profile
        org = profile.org
        is_admin = profile.role == "ADMIN" or request.user.is_superuser
        if not is_admin:
            return Response(
                {"error": True, "errors": "Admin access required"},
                status=status.HTTP_403_FORBIDDEN,
            )

        today = date.today()
        leads = Lead.objects.filter(org=org)
        # "Open" = still being worked (excludes won/lost end states).
        open_q = ~Q(status__in=["converted", "closed"])

        total = leads.count()
        assigned = leads.filter(assigned_to__isnull=False).distinct().count()
        converted = leads.filter(status="converted").count()
        overview = {
            "total": total,
            "assigned": assigned,
            "unassigned": total - assigned,
            "converted": converted,
            "conversion_rate": round(converted / total * 100, 1) if total else 0,
        }

        # Status breakdown (label blank/null status as "unset").
        status_breakdown = []
        for row in (
            leads.values("status").annotate(count=Count("id")).order_by("-count")
        ):
            status_breakdown.append(
                {"status": row["status"] or "unset", "count": row["count"]}
            )

        followup_health = {
            "due_today": leads.filter(open_q, next_follow_up=today).count(),
            "overdue": leads.filter(open_q, next_follow_up__lt=today).count(),
            "never_contacted": leads.filter(
                open_q, assigned_to__isnull=False, last_contacted__isnull=True
            )
            .distinct()
            .count(),
            "upcoming": leads.filter(open_q, next_follow_up__gt=today).count(),
        }

        # Per-rep metrics — one grouped query each, merged by profile id.
        def by_rep(qs):
            return {
                row["assigned_to"]: row["c"]
                for row in qs.filter(assigned_to__isnull=False)
                .values("assigned_to")
                .annotate(c=Count("id", distinct=True))
            }

        assigned_map = by_rep(leads)
        contacted_map = by_rep(leads.filter(last_contacted__isnull=False))
        converted_map = by_rep(leads.filter(status="converted"))
        overdue_map = by_rep(leads.filter(open_q, next_follow_up__lt=today))
        uncontacted_map = by_rep(leads.filter(open_q, last_contacted__isnull=True))

        user_metrics = []
        for p in Profile.objects.filter(org=org, is_active=True).select_related("user"):
            a = assigned_map.get(p.id, 0)
            user_metrics.append(
                {
                    "id": str(p.id),
                    "name": (getattr(p.user, "name", "") or "").strip()
                    or (p.user.email if p.user else "Unknown"),
                    "email": p.user.email if p.user else "",
                    "assigned": a,
                    "contacted": contacted_map.get(p.id, 0),
                    "converted": converted_map.get(p.id, 0),
                    "overdue": overdue_map.get(p.id, 0),
                    "never_contacted": uncontacted_map.get(p.id, 0),
                }
            )
        # Most-loaded reps first.
        user_metrics.sort(key=lambda m: m["assigned"], reverse=True)

        # Recent lead-activity feed (latest 50) with touch count + last outcome.
        latest_outcome = (
            LeadInteraction.objects.filter(lead=OuterRef("pk"))
            .order_by("-occurred_at")
            .values("outcome")[:1]
        )
        activity_qs = (
            leads.annotate(
                interaction_count=Count("interactions", distinct=True),
                latest_outcome=Subquery(latest_outcome),
            )
            .order_by("-created_at")
            .prefetch_related("assigned_to__user")[:50]
        )
        lead_activity = []
        for lead in activity_qs:
            assignees = list(lead.assigned_to.all())
            is_open = lead.status not in ("converted", "closed")
            attention = ""
            if is_open and lead.next_follow_up and lead.next_follow_up < today:
                attention = "overdue"
            elif is_open and assignees and lead.last_contacted is None:
                attention = "never_contacted"
            lead_activity.append(
                {
                    "id": str(lead.id),
                    "name": str(lead),
                    "company": lead.company_name,
                    "owner": (
                        (assignees[0].user.email if assignees[0].user else None)
                        if assignees
                        else None
                    ),
                    "owner_count": len(assignees),
                    "status": lead.status,
                    "rating": lead.rating,
                    "created_at": lead.created_at.isoformat() if lead.created_at else None,
                    "last_contacted": lead.last_contacted.isoformat()
                    if lead.last_contacted
                    else None,
                    "next_follow_up": lead.next_follow_up.isoformat()
                    if lead.next_follow_up
                    else None,
                    "interaction_count": lead.interaction_count,
                    "latest_outcome": lead.latest_outcome,
                    "attention": attention,
                }
            )

        return Response(
            {
                "error": False,
                "overview": overview,
                "status_breakdown": status_breakdown,
                "followup_health": followup_health,
                "user_metrics": user_metrics,
                "lead_activity": lead_activity,
            },
            status=status.HTTP_200_OK,
        )
