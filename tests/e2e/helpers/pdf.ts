/** Throws unless `buf` looks like a valid, non-empty PDF. Returns the page count (best-effort). */
export function assertValidPdf(buf: Buffer): number {
  if (!buf || buf.length === 0) throw new Error('PDF buffer is empty');
  const head = buf.subarray(0, 5).toString('latin1');
  if (head !== '%PDF-') throw new Error(`Buffer is not a PDF (header was "${head}")`);
  const tail = buf.subarray(-1024).toString('latin1');
  if (!tail.includes('%%EOF')) throw new Error('PDF is missing %%EOF trailer');
  const matches = buf.toString('latin1').match(/\/Type\s*\/Page[^s]/g);
  return matches ? matches.length : 0;
}
