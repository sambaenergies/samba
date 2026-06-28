/** Coerce a number `<input>`'s value to `number | null` (empty → null).
 *
 * `v-model.number` writes back the raw `""` when a field is cleared (parseFloat("")
 * is NaN), which is invalid for nullable schema fields (capacity "blank = auto",
 * budget "blank = unlimited", …) and disables Run. Bind such inputs with
 * `:value` + `@input="x = toNumberOrNull($event)"` instead.
 */
export function toNumberOrNull(event: Event): number | null {
  const raw = (event.target as HTMLInputElement).value;
  return raw === "" ? null : Number(raw);
}
