import { type Page, type Locator, expect } from '@playwright/test';

/** The Song Database tab — add/search/delete songs. */
export class SongDbPage {
  constructor(private readonly page: Page) {}

  search(): Locator {
    return this.page.locator('#song-db-search');
  }

  rows(): Locator {
    return this.page.locator('[data-testid="song-db-row"]');
  }

  rowByTitle(title: string): Locator {
    return this.page
      .locator('[data-testid="song-db-row"]')
      .filter({ has: this.page.locator('.song-db-entry-title', { hasText: title }) });
  }

  /** Fill the add-song form and save; waits for the /api/songs POST to land. */
  async add(title: string, author: string, lyrics: string, copyright: string): Promise<void> {
    await this.page.locator('#sdb-title').fill(title);
    await this.page.locator('#sdb-author').fill(author);
    await this.page.locator('#sdb-lyrics').fill(lyrics);
    await this.page.locator('#sdb-copyright').fill(copyright);
    const saved = this.page.waitForResponse(
      (r) => r.url().includes('/api/songs') && r.request().method() === 'POST' && r.ok(),
      { timeout: 15_000 },
    );
    await this.page.locator('#sdb-save-btn').click();
    await saved;
  }

  /** Delete a song via its row's delete button (native confirm auto-accepted). */
  async deleteByTitle(title: string): Promise<void> {
    await this.rowByTitle(title).getByTitle('Delete song').click();
    await expect(this.rowByTitle(title)).toHaveCount(0);
  }
}
