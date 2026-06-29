<script>
  import { Button } from '$lib/components/ui/button/index.js';
  import { UserPlus, Phone, Mail, ChevronRight, ArrowRight, PhoneCall } from '@lucide/svelte';

  /**
   * @typedef {Object} Lead
   * @property {string} id
   * @property {string} [first_name]
   * @property {string} [last_name]
   * @property {string} [company]
   * @property {string} [phone]
   * @property {string} [email]
   * @property {string} [created_at]
   */

  /**
   * @typedef {Object} Props
   * @property {Lead[]} [leads] - Newly assigned, uncontacted leads
   * @property {number} [total] - Total count (may exceed shown list)
   */

  /** @type {Props} */
  let { leads = [], total = 0 } = $props();

  const count = $derived(total || leads.length);

  /**
   * Get lead name
   * @param {Lead} lead
   */
  function getLeadName(lead) {
    const parts = [lead.first_name, lead.last_name].filter(Boolean);
    return parts.length > 0 ? parts.join(' ') : 'Unnamed Lead';
  }

  /**
   * Relative "assigned" time, e.g. "Today", "2d ago"
   * @param {string | null | undefined} dateStr
   */
  function assignedAgo(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const dOnly = new Date(d);
    dOnly.setHours(0, 0, 0, 0);
    const days = Math.round((today.getTime() - dOnly.getTime()) / (1000 * 60 * 60 * 24));
    if (days <= 0) return 'New today';
    if (days === 1) return '1d ago';
    return `${days}d ago`;
  }
</script>

<div
  class="overflow-hidden rounded-[var(--radius-xl)] border border-[var(--color-primary-default)]/30 bg-[var(--color-primary-light)] shadow-[var(--shadow-sm)] dark:border-[var(--color-primary-default)]/25 dark:bg-[var(--color-primary-default)]/10 dark:backdrop-blur-sm"
>
  <!-- Header -->
  <div
    class="flex items-center justify-between border-b border-[var(--color-primary-default)]/20 px-5 py-4"
  >
    <div class="flex items-center gap-3">
      <div
        class="flex size-9 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-default)]/15"
      >
        <UserPlus class="size-5 text-[var(--color-primary-default)]" />
      </div>
      <div>
        <div class="flex items-center gap-2">
          <h2 class="text-base font-semibold tracking-tight text-[var(--text-primary)]">
            New Leads to Contact
          </h2>
          <span
            class="inline-flex min-w-5 items-center justify-center rounded-full bg-[var(--color-primary-default)] px-1.5 text-xs font-bold text-white tabular-nums"
          >
            {count}
          </span>
        </div>
        <p class="text-xs text-[var(--text-tertiary)]">
          Assigned to you and not contacted yet — reach out first
        </p>
      </div>
    </div>
    <Button
      variant="ghost"
      size="sm"
      href="/leads"
      class="gap-1 text-xs font-medium"
    >
      View all
      <ChevronRight class="size-3.5" />
    </Button>
  </div>

  <!-- Leads list -->
  <div class="divide-y divide-[var(--color-primary-default)]/10">
    {#each leads as lead (lead.id)}
      <a
        href="/leads?view={lead.id}"
        class="group flex items-center gap-3 px-5 py-3 transition-colors hover:bg-[var(--color-primary-default)]/10"
      >
        <!-- Lead info -->
        <div class="min-w-0 flex-1">
          <p
            class="truncate text-sm font-medium text-[var(--text-primary)] transition-colors group-hover:text-[var(--color-primary-default)]"
          >
            {getLeadName(lead)}
          </p>
          <p class="mt-0.5 truncate text-xs text-[var(--text-secondary)]">
            {lead.company || 'No company'}
          </p>
        </div>

        <!-- Assigned time -->
        <span class="flex-shrink-0 text-xs font-medium text-[var(--text-tertiary)] tabular-nums">
          {assignedAgo(lead.created_at)}
        </span>

        <!-- Quick contact actions -->
        <div class="flex flex-shrink-0 items-center gap-1">
          {#if lead.phone}
            <Button
              variant="ghost"
              size="icon"
              href="tel:{lead.phone}"
              class="size-7 rounded-[var(--radius-md)] hover:bg-[var(--activity-call)]/10 hover:text-[var(--activity-call)]"
              title="Call {lead.phone}"
              onclick={(e) => e.stopPropagation()}
            >
              <Phone class="size-3.5" />
            </Button>
          {/if}
          {#if lead.email}
            <Button
              variant="ghost"
              size="icon"
              href="mailto:{lead.email}"
              class="size-7 rounded-[var(--radius-md)] hover:bg-[var(--activity-email)]/10 hover:text-[var(--activity-email)]"
              title="Email {lead.email}"
              onclick={(e) => e.stopPropagation()}
            >
              <Mail class="size-3.5" />
            </Button>
          {/if}
          <Button
            variant="ghost"
            size="icon"
            href="/leads/{lead.id}?log=1"
            class="size-7 rounded-[var(--radius-md)] hover:bg-[var(--color-primary-default)]/10 hover:text-[var(--color-primary-default)]"
            title="Log contact"
            onclick={(e) => e.stopPropagation()}
          >
            <PhoneCall class="size-3.5" />
          </Button>
          <ArrowRight
            class="size-4 text-[var(--text-tertiary)] opacity-0 transition-opacity group-hover:opacity-100"
          />
        </div>
      </a>
    {/each}
  </div>
</div>
