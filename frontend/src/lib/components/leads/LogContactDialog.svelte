<script>
  import { enhance } from '$app/forms';
  import { invalidateAll } from '$app/navigation';
  import { toast } from 'svelte-sonner';
  import * as Dialog from '$lib/components/ui/dialog/index.js';
  import * as Select from '$lib/components/ui/select/index.js';
  import { Button } from '$lib/components/ui/button/index.js';
  import { Label } from '$lib/components/ui/label/index.js';
  import { Textarea } from '$lib/components/ui/textarea/index.js';
  import { Input } from '$lib/components/ui/input/index.js';
  import { Phone, Mail, Users, FileText } from '@lucide/svelte';

  /**
   * @typedef {Object} Props
   * @property {boolean} [open]
   * @property {string} leadId
   * @property {{ value: string, label: string }[]} [outcomeOptions]
   * @property {() => void} [onLogged] - called after a successful log (e.g. to refresh the drawer)
   */

  /** @type {Props} */
  let { open = $bindable(false), leadId, outcomeOptions = [], onLogged } = $props();

  const TYPE_OPTIONS = [
    { value: 'call', label: 'Call', icon: Phone },
    { value: 'email', label: 'Email', icon: Mail },
    { value: 'meeting', label: 'Meeting', icon: Users },
    { value: 'note', label: 'Note', icon: FileText }
  ];

  let interactionType = $state('call');
  let outcome = $state('');
  let notes = $state('');
  let nextFollowUp = $state('');
  let submitting = $state(false);

  const typeLabel = $derived(
    TYPE_OPTIONS.find((t) => t.value === interactionType)?.label ?? 'Call'
  );
  const outcomeLabel = $derived(
    outcomeOptions.find((o) => o.value === outcome)?.label ?? 'Select outcome'
  );

  function resetForm() {
    interactionType = 'call';
    outcome = '';
    notes = '';
    nextFollowUp = '';
  }

  // Reset whenever the dialog opens.
  $effect(() => {
    if (open) resetForm();
  });
</script>

<Dialog.Root bind:open>
  <Dialog.Content class="sm:max-w-[480px]">
    <Dialog.Header>
      <Dialog.Title>Log Contact</Dialog.Title>
      <Dialog.Description>
        Record this touch. It updates the lead's last-contacted date and, if you set a
        follow-up, schedules the next one.
      </Dialog.Description>
    </Dialog.Header>

    <form
      method="POST"
      action="?/logContact"
      use:enhance={() => {
        submitting = true;
        return async ({ result }) => {
          submitting = false;
          if (result.type === 'success') {
            toast.success('Contact logged');
            open = false;
            await invalidateAll();
            onLogged?.();
          } else if (result.type === 'failure') {
            toast.error(/** @type {any} */ (result.data)?.error || 'Failed to log contact');
          } else if (result.type === 'error') {
            toast.error('An unexpected error occurred');
          }
        };
      }}
      class="space-y-4 py-2"
    >
      <input type="hidden" name="leadId" value={leadId} />
      <input type="hidden" name="interaction_type" value={interactionType} />
      <input type="hidden" name="outcome" value={outcome} />

      <div class="space-y-1.5">
        <Label>Type</Label>
        <Select.Root type="single" bind:value={interactionType}>
          <Select.Trigger class="w-full">{typeLabel}</Select.Trigger>
          <Select.Content>
            {#each TYPE_OPTIONS as opt (opt.value)}
              <Select.Item value={opt.value}>{opt.label}</Select.Item>
            {/each}
          </Select.Content>
        </Select.Root>
      </div>

      {#if outcomeOptions.length > 0}
        <div class="space-y-1.5">
          <Label>Outcome <span class="text-[color:var(--text-subtle)]">(optional)</span></Label>
          <Select.Root type="single" bind:value={outcome}>
            <Select.Trigger class="w-full">{outcomeLabel}</Select.Trigger>
            <Select.Content>
              {#each outcomeOptions as opt (opt.value)}
                <Select.Item value={opt.value}>{opt.label}</Select.Item>
              {/each}
            </Select.Content>
          </Select.Root>
        </div>
      {/if}

      <div class="space-y-1.5">
        <Label for="log-notes">Notes <span class="text-[color:var(--color-negative-default)]">*</span></Label>
        <Textarea
          id="log-notes"
          name="notes"
          bind:value={notes}
          required
          rows={4}
          placeholder="What happened? e.g. Left a voicemail, will retry Thursday."
        />
      </div>

      <div class="space-y-1.5">
        <Label for="log-followup">Next follow-up <span class="text-[color:var(--text-subtle)]">(optional)</span></Label>
        <Input id="log-followup" name="next_follow_up" type="date" bind:value={nextFollowUp} />
      </div>

      <Dialog.Footer>
        <Button type="button" variant="ghost" onclick={() => (open = false)}>Cancel</Button>
        <Button type="submit" disabled={submitting || !notes.trim()}>
          {submitting ? 'Logging…' : 'Log Contact'}
        </Button>
      </Dialog.Footer>
    </form>
  </Dialog.Content>
</Dialog.Root>
