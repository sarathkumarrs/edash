<script>
  import { DollarSign, TrendingUp, Target, Percent, AlertCircle } from '@lucide/svelte';
  import {
    KPICard,
    FocusBar,
    GoalProgress,
    MiniPipeline,
    PipelineChart,
    TaskList,
    HotLeadsPanel,
    NewLeadsBanner,
    OpportunitiesTable,
    ActivityFeed
  } from '$lib/components/dashboard';
  import { formatCurrency } from '$lib/utils/formatting.js';
  import { orgSettings } from '$lib/stores/org.js';
  import { isModuleEnabled } from '$lib/modules';

  const today = new Date().toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric'
  });

  /** @type {{ data: any }} */
  let { data } = $props();

  const metrics = $derived(data.metrics || {});
  const recentData = $derived(data.recentData || {});
  const urgentCounts = $derived(data.urgentCounts || {});
  const pipelineByStage = $derived(data.pipelineByStage || {});
  const revenueMetrics = $derived(data.revenueMetrics || {});
  const hotLeads = $derived(data.hotLeads || []);
  const newLeads = $derived(data.newLeads || []);
  const goalSummary = $derived(data.goalSummary || []);

  // Hide widgets for modules this workspace has disabled.
  const showDeals = $derived(isModuleEnabled(data.enabled_modules, 'deals'));
  const showGoals = $derived(isModuleEnabled(data.enabled_modules, 'goals'));
  const showTasks = $derived(isModuleEnabled(data.enabled_modules, 'tasks'));
  const showLeads = $derived(isModuleEnabled(data.enabled_modules, 'leads'));

  // Get org's default currency for KPI display
  const orgCurrency = $derived($orgSettings.default_currency || 'USD');
  const otherCurrencyCount = $derived(revenueMetrics.other_currency_count || 0);
  const currencyNote = $derived(
    otherCurrencyCount > 0
      ? `${orgCurrency} only (${otherCurrencyCount} in other currencies)`
      : `${orgCurrency} only`
  );

</script>

<svelte:head>
  <title>Dashboard - EdashCRM</title>
</svelte:head>

<div class="min-h-screen">
  <div class="px-7 pt-6 md:px-8">
    <p class="label-tiny">Today · {today}</p>
  </div>

  <div class="space-y-8 p-6 md:p-8">
    {#if data.error}
      <div
        class="flex items-center gap-4 rounded-[var(--radius-lg)] border border-[var(--color-negative-default)]/20 bg-[var(--color-negative-light)] p-5 backdrop-blur-sm dark:border-[var(--color-negative-default)]/30 dark:bg-[var(--color-negative-default)]/10"
      >
        <div
          class="flex size-10 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-negative-light)] dark:bg-[var(--color-negative-default)]/20"
        >
          <AlertCircle class="size-5 text-[var(--color-negative-default)]" />
        </div>
        <div>
          <p class="text-sm font-medium text-[var(--color-negative-default)]">
            Error loading dashboard
          </p>
          <p class="text-xs text-[var(--color-negative-default)]/80">{data.error}</p>
        </div>
      </div>
    {:else}
      <!-- Focus Bar - Urgent Items with premium styling -->
      <div>
        <FocusBar
          overdueCount={urgentCounts.overdue_tasks || 0}
          todayCount={urgentCounts.tasks_due_today || 0}
          followupsCount={urgentCounts.followups_today || 0}
          hotLeadsCount={urgentCounts.hot_leads || 0}
        />
      </div>

      {#if showLeads && newLeads.length > 0}
        <!-- New Leads to Contact - prominent banner for first-touch follow-up -->
        <div>
          <NewLeadsBanner leads={newLeads} total={urgentCounts.new_leads || newLeads.length} />
        </div>
      {/if}

      {#if showDeals}
      <!-- Pipeline Overview - Full Width with glass effect -->
      <div
        class="rounded-[var(--radius-xl)] border border-[var(--border-default)] bg-[var(--surface-raised)] p-6 shadow-[var(--shadow-sm)] dark:bg-[var(--surface-raised)]/80 dark:shadow-lg dark:shadow-black/10 dark:backdrop-blur-sm"
      >
        <div class="mb-5 flex items-center justify-between">
          <div class="flex items-center gap-3">
            <div
              class="flex size-9 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] dark:bg-[var(--color-primary-default)]/15"
            >
              <TrendingUp class="size-5 text-[var(--color-primary-default)]" />
            </div>
            <div>
              <h2 class="text-base font-semibold tracking-tight text-[var(--text-primary)]">
                Sales Pipeline
              </h2>
              <p class="text-xs text-[var(--text-tertiary)]">{currencyNote}</p>
            </div>
          </div>
        </div>
        <MiniPipeline pipelineData={pipelineByStage} currency={orgCurrency} />
      </div>
      {/if}

      {#if showDeals}
      <!-- Revenue Metrics Grid - 4 columns with hover effects -->
      <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KPICard
          label="Pipeline Value"
          value={formatCurrency(revenueMetrics.pipeline_value || 0, orgCurrency, true)}
          subtitle={currencyNote}
          accentColor="orange"
        >
          {#snippet icon()}
            <DollarSign class="size-5" />
          {/snippet}
        </KPICard>
        <KPICard
          label="Weighted Pipeline"
          value={formatCurrency(revenueMetrics.weighted_pipeline || 0, orgCurrency, true)}
          subtitle={currencyNote}
          accentColor="violet"
        >
          {#snippet icon()}
            <TrendingUp class="size-5" />
          {/snippet}
        </KPICard>
        <KPICard
          label="Won This Month"
          value={formatCurrency(revenueMetrics.won_this_month || 0, orgCurrency, true)}
          subtitle={currencyNote}
          accentColor="emerald"
        >
          {#snippet icon()}
            <Target class="size-5" />
          {/snippet}
        </KPICard>
        <KPICard
          label="Conversion Rate"
          value="{revenueMetrics.conversion_rate || 0}%"
          accentColor="amber"
        >
          {#snippet icon()}
            <Percent class="size-5" />
          {/snippet}
        </KPICard>
      </div>
      {/if}

      <!-- Pipeline Chart + Hot Leads -->
      <div class="grid grid-cols-1 gap-6 lg:grid-cols-5">
        {#if showDeals}
        <div class="lg:col-span-3">
          <PipelineChart pipelineData={pipelineByStage} currency={orgCurrency} />
        </div>
        {/if}
        {#if showLeads}
        <div class="lg:col-span-2">
          <HotLeadsPanel leads={hotLeads} />
        </div>
        {/if}
      </div>

      <!-- Tasks + Opportunities + Goals -->
      <div class="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {#if showTasks}<TaskList tasks={recentData.tasks || []} />{/if}
        {#if showDeals}<OpportunitiesTable opportunities={recentData.opportunities || []} />{/if}
        {#if showGoals}<GoalProgress goals={goalSummary} />{/if}
      </div>

      <!-- Activity Feed - Full Width -->
      <div>
        <ActivityFeed activities={recentData.activities || []} />
      </div>
    {/if}
  </div>
</div>
