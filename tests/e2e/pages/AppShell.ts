import { type Page, type Locator, expect } from '@playwright/test';

const TABS = {
  editor: 'page-editor',
  files: 'page-files',
  songdb: 'page-songdb',
  format: 'page-format',
  templates: 'page-templates',
  settings: 'page-settings',
} as const;
export type TabName = keyof typeof TABS;

export class AppShell {
  constructor(private readonly page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto('/');
    await expect(this.page.locator('.tab-bar')).toBeVisible();
  }

  tab(name: TabName): Locator {
    return this.page.locator(`[data-tab="${TABS[name]}"]`);
  }

  async switchTo(name: TabName): Promise<void> {
    await this.tab(name).click();
    await expect(this.tab(name)).toHaveAttribute('aria-selected', 'true');
  }

  /**
   * Assert the server-mode session is authenticated. Uses UI signals, NOT
   * page.request — page.request is a separate context that does not run the
   * app's JS, so it never attaches the supabase Bearer token that apiFetch adds.
   */
  async expectAuthenticated(): Promise<void> {
    await expect(this.page.locator('#login-screen')).toBeHidden();
    await expect(this.page.locator('#user-info')).toBeVisible();
  }
}
