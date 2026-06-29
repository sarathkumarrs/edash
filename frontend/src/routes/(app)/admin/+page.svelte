<script>
  import { PageHeader } from '$lib/components/layout';
  import { KPICard } from '$lib/components/dashboard';
  import { SectionCard } from '$lib/components/ui/section-card/index.js';
  import { Badge } from '$lib/components/ui/badge/index.js';
  import { Users, UserCheck, UserX, TrendingUp, CalendarClock, AlertTriangle, PhoneOff, CalendarDays } from '@lucide/svelte';
  import { formatDate, formatRelativeDate } from '$lib/utils/formatting.js';

  /** @type {{ data: { overview: any, statusBreakdown: any[], followupHealth: any, userMetrics: any[], leadActivity: any[] } }} */
  let { data } = $props();

  const overview = $derived(data.overview || {});
  const statusBreakdown = $derived(data.statusBreakdown || []);
  const health = $derived(data.followupHealth || {});
  const userMetrics = $derived(data.userMetrics || []);
  const leadActivity = $derived(data.leadActivity || []);

  const totalForBars = $derived(
    statusBreakdown.reduce((/** @type {number} */ s, /** @type {any} */ r) => s + r.count, 0) || 1
  );

  /** @param {string} s */
  function titleCase(s) {
    return (s || '').replace(/(^|\s)\w/g, (c) => c.toUpperCase());
  }

  const STATUS_COLORS = /** @type {Record<string, string>} */ ({
    assigned: 'var(--color-primary-default)',
    'in process': 'var(--lead-warm, #d97706)',
    converted: 'var(--color-positive-default, #16a34a)',
    recycled: 'var(--text-subtle)',
    closed: 'var(--text-subtle)',
    unset: 'var(--text-subtle)'
  });
</script>

<svelte:head><title>Admin Overview - EdashCRM</title></svelte:head>

<PageHeader title="Admin Overview" subtitle="Organization-wide lead & team health" />

<div class="space-y-6 px-7 py-6 md:px-8">
  <!-- Overview KPIs -->
  <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
    <KPICard label="Total Leads" value={overview.total ?? 0} accentColor="blue">
      {#snippet icon()}<Users class="size-5" />{/snippet}
    </KPICard>
    <KPICard label="Assigned" value={overview.assigned ?? 0} accentColor="emerald">
      {#snippet icon()}<UserCheck class="size-5" />{/snippet}
    </KPICard>
    <KPICard
      label="Unassigned"
      value={overview.unassigned ?? 0}
      subtitle={overview.unassigned ? 'Needs an owner' : 'All assigned'}
      accentColor="amber"
    >
      {#snippet icon()}<UserX class="size-5" />{/snippet}
    </KPICard>
    <KPICard
      label="Conversion Rate"
      value="{overview.conversion_rate ?? 0}%"
      subtitle="{overview.converted ?? 0} converted"
      accentColor="violet"
    >
      {#snippet icon()}<TrendingUp class="size-5" />{/snippet}
    </KPICard>
  </div>

  <!-- Follow-up health -->
  <SectionCard title="Follow-up health">
    <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {#each [{ label: 'Due today', value: health.due_today ?? 0, icon: CalendarClock, color: 'var(--color-primary-default)' }, { label: 'Overdue (missed)', value: health.overdue ?? 0, icon: AlertTriangle, color: 'var(--color-negative-default, #dc2626)' }, { label: 'Never contacted', value: health.never_contacted ?? 0, icon: PhoneOff, color: 'var(--lead-warm, #d97706)' }, { label: 'Upcoming', value: health.upcoming ?? 0, icon: CalendarDays, color: 'var(--text-muted)' }] as tile (tile.label)}
        <div class="rounded-[var(--radius-lg)] border border-[var(--border-default)] p-4">
          <div class="flex items-center gap-2 text-[color:var(--text-subtle)]">
            <tile.icon class="size-4" style="color:{tile.color}" />
            <span class="text-xs font-medium">{tile.label}</span>
          </div>
          <p class="mt-2 text-2xl font-bold tabular-nums" style="color:{tile.color}">
            {tile.value}
          </p>
        </div>
      {/each}
    </div>
  </SectionCard>

  <!-- Status breakdown -->
  {#if statusBreakdown.length > 0}
    <SectionCard title="Leads by status">
      <div class="space-y-2.5">
        {#each statusBreakdown as row (row.status)}
          <div class="flex items-center gap-3">
            <span class="w-28 shrink-0 text-[13px] text-[color:var(--text-muted)]">
              {titleCase(row.status)}
            </span>
            <div class="h-2.5 flex-1 overflow-hidden rounded-full bg-[color:var(--bg-elevated)]">
              <div
                class="h-full rounded-full"
                style="width:{(row.count / totalForBars) * 100}%; background:{STATUS_COLORS[
                  row.status
                ] || 'var(--color-primary-default)'}"
              ></div>
            </div>
            <span class="w-10 shrink-0 text-right text-[13px] font-medium tabular-nums">
              {row.count}
            </span>
          </div>
        {/each}
      </div>
    </SectionCard>
  {/if}

  <!-- User performance -->
  <SectionCard title="Team performance">
    {#if userMetrics.length === 0}
      <p class="text-[13px] italic text-[color:var(--text-subtle)]">No active members.</p>
    {:else}
      <div class="overflow-x-auto">
        <table class="w-full text-[13px]">
          <thead>
            <tr class="border-b border-[color:var(--border-default)] text-left text-[color:var(--text-subtle)]">
              <th class="px-2 py-2 font-medium">Member</th>
              <th class="px-2 py-2 text-right font-medium">Assigned</th>
              <th class="px-2 py-2 text-right font-medium">Contacted</th>
              <th class="px-2 py-2 text-right font-medium">Converted</th>
              <th class="px-2 py-2 text-right font-medium">Overdue</th>
              <th class="px-2 py-2 text-right font-medium">Uncontacted</th>
            </tr>
          </thead>
          <tbody>
            {#each userMetrics as m (m.id)}
              <tr class="border-b border-[color:var(--border-faint)]">
                <td class="px-2 py-2">
                  <div class="font-medium text-[color:var(--text-primary)]">{m.name}</div>
                  <div class="text-[11px] text-[color:var(--text-subtle)]">{m.email}</div>
                </td>
                <td class="px-2 py-2 text-right tabular-nums">{m.assigned}</td>
                <td class="px-2 py-2 text-right tabular-nums">{m.contacted}</td>
                <td class="px-2 py-2 text-right tabular-nums">{m.converted}</td>
                <td
                  class="px-2 py-2 text-right tabular-nums {m.overdue > 0
                    ? 'font-semibold text-[color:var(--color-negative-default,#dc2626)]'
                    : ''}"
                >
                  {m.overdue}
                </td>
                <td
                  class="px-2 py-2 text-right tabular-nums {m.never_contacted > 0
                    ? 'font-semibold text-[color:var(--lead-warm,#d97706)]'
                    : ''}"
                >
                  {m.never_contacted}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </SectionCard>

  <!-- Recent lead activity -->
  <SectionCard title="Recent lead activity">
    {#if leadActivity.length === 0}
      <p class="text-[13px] italic text-[color:var(--text-subtle)]">No leads yet.</p>
    {:else}
      <div class="overflow-x-auto">
        <table class="w-full text-[13px]">
          <thead>
            <tr class="border-b border-[color:var(--border-default)] text-left text-[color:var(--text-subtle)]">
              <th class="px-2 py-2 font-medium">Lead</th>
              <th class="px-2 py-2 font-medium">Owner</th>
              <th class="px-2 py-2 font-medium">Status</th>
              <th class="px-2 py-2 font-medium">Created</th>
              <th class="px-2 py-2 font-medium">Last contact</th>
              <th class="px-2 py-2 font-medium">Follow-up</th>
              <th class="px-2 py-2 text-right font-medium">Touches</th>
              <th class="px-2 py-2 font-medium">Flag</th>
            </tr>
          </thead>
          <tbody>
            {#each leadActivity as l (l.id)}
              <tr class="border-b border-[color:var(--border-faint)] hover:bg-[color:var(--bg-elevated)]">
                <td class="px-2 py-2">
                  <a href="/leads/{l.id}" class="font-medium text-[color:var(--text-primary)] hover:text-[color:var(--color-primary-default)]">
                    {l.name}
                  </a>
                  {#if l.company}
                    <div class="text-[11px] text-[color:var(--text-subtle)]">{l.company}</div>
                  {/if}
                </td>
                <td class="px-2 py-2 text-[color:var(--text-muted)]">
                  {#if l.owner}
                    {l.owner}{#if l.owner_count > 1}
                      <span class="text-[color:var(--text-subtle)]">+{l.owner_count - 1}</span>
                    {/if}
                  {:else}
                    <span class="text-[color:var(--text-subtle)]">Unassigned</span>
                  {/if}
                </td>
                <td class="px-2 py-2 text-[color:var(--text-muted)]">{titleCase(l.status)}</td>
                <td class="px-2 py-2 text-[color:var(--text-muted)]">
                  {l.created_at ? formatRelativeDate(l.created_at) : '—'}
                </td>
                <td class="px-2 py-2 text-[color:var(--text-muted)]">
                  {l.last_contacted ? formatRelativeDate(l.last_contacted) : '—'}
                </td>
                <td class="px-2 py-2 text-[color:var(--text-muted)]">
                  {l.next_follow_up ? formatDate(l.next_follow_up) : '—'}
                </td>
                <td class="px-2 py-2 text-right tabular-nums">{l.interaction_count}</td>
                <td class="px-2 py-2">
                  {#if l.attention === 'overdue'}
                    <Badge class="bg-[color:var(--color-negative-light,#fee2e2)] text-[color:var(--color-negative-default,#dc2626)]">Overdue</Badge>
                  {:else if l.attention === 'never_contacted'}
                    <Badge class="bg-[color:var(--lead-warm-bg,#fef3c7)] text-[color:var(--lead-warm,#d97706)]">No contact</Badge>
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <p class="mt-3 text-[12px] text-[color:var(--text-subtle)]">
        Showing the {leadActivity.length} most recent leads.
        <a href="/leads" class="text-[color:var(--color-primary-default)] hover:underline">View all leads →</a>
      </p>
    {/if}
  </SectionCard>
</div>
