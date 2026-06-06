import { type Page, type Locator, expect } from '@playwright/test';

/** The Projects (Files) tab — saved-project list and per-card actions. */
export class ProjectsPage {
  constructor(private readonly page: Page) {}

  list(): Locator {
    return this.page.locator('#files-list');
  }

  cards(): Locator {
    return this.page.locator('#files-list .file-card');
  }

  /** A project card located by its visible name. */
  cardByName(name: string): Locator {
    return this.page
      .locator('#files-list .file-card')
      .filter({ has: this.page.locator('.file-card-name', { hasText: name }) });
  }

  /** Load a project into the editor via its card's Load button. */
  async loadByName(name: string): Promise<void> {
    await this.cardByName(name).locator('[data-fm="load"]').click();
  }

  /**
   * Load a project by its exact id. Prefer this over loadByName when another
   * member must open *a specific* project (e.g. presence tests): a same-named
   * stray duplicate would make loadByName ambiguous (strict-mode violation) and
   * could target the wrong project id, missing the owner's heartbeat. The Load
   * button carries `data-id="<project.id>"`.
   */
  async loadById(id: string): Promise<void> {
    await this.page.locator(`#files-list .file-card [data-fm="load"][data-id="${id}"]`).click();
  }

  /** Delete a project via its card's Delete button (native confirm auto-accepted). */
  async deleteByName(name: string): Promise<void> {
    await this.cardByName(name).locator('[data-fm="delete"]').click();
    await expect(this.cardByName(name)).toHaveCount(0);
  }

  /** Select a project's checkbox (drives the bulk-actions bar). */
  async toggleSelect(name: string): Promise<void> {
    await this.cardByName(name).locator('.file-card-cb').click();
  }

  bulkBar(): Locator {
    return this.page.locator('#bulk-bar');
  }
}
