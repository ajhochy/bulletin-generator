import { describe, it, expect } from 'vitest';
import { assertValidPdf } from './pdf';

describe('assertValidPdf', () => {
  it('accepts a minimal PDF buffer', () => {
    const buf = Buffer.from('%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF');
    expect(() => assertValidPdf(buf)).not.toThrow();
  });
  it('rejects non-PDF bytes', () => {
    expect(() => assertValidPdf(Buffer.from('<html></html>'))).toThrow(/not a PDF/i);
  });
  it('rejects an empty buffer', () => {
    expect(() => assertValidPdf(Buffer.alloc(0))).toThrow(/empty/i);
  });
});
