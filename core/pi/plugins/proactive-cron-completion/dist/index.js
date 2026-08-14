import { finalizeCronCompletion } from "../../../tools/proactive_completion.mjs";

export async function handleCronChanged(event, finalize = finalizeCronCompletion) {
  if (!event || event.action !== "finished") return { handled: false, reason: "not-finished" };
  const result = await finalize({
    cronId: event.jobId,
    runStatus: event.status,
    deliveryStatus: event.deliveryStatus,
    delivered: event.delivered
  });
  return { handled: true, ...result };
}

export default {
  id: "proactive-cron-completion",
  name: "Proactive Cron Completion",
  description: "Finalizes a bound time Commitment only after an OpenClaw Cron announce is confirmed delivered.",
  register(api) {
    api.on("cron_changed", async (event) => {
      await handleCronChanged(event);
    });
  }
};
