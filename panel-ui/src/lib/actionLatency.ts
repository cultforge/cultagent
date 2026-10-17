/** Start is immediate; stop/restart wait briefly so mis-clicks are less painful. */

const STOP_RESTART_DELAY_MS = 550;

export async function runServerAction(
  action: "start" | "stop" | "restart",
  execute: () => Promise<unknown>,
): Promise<void> {
  if (action === "stop" || action === "restart") {
    await new Promise((r) => setTimeout(r, STOP_RESTART_DELAY_MS));
  }
  await execute();
}
