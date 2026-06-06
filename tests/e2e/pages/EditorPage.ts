import { type Page, type Locator, expect } from '@playwright/test';
import { expandSection, row } from './common';

/** The Booklet Editor — Order of Worship item list and the live preview. */
export class EditorPage {
  constructor(private readonly page: Page) {}

  /** Expand the (initially collapsed) Order of Worship section. */
  async openOrderOfWorship(): Promise<void> {
    await expandSection(this.page, 'Order of Worship');
  }

  items(): Locator {
    return this.page.locator('[data-testid="item-row"]');
  }

  item(index: number): Locator {
    return row(this.page, 'item', index);
  }

  preview(): Locator {
    return this.page.locator('#preview-pane');
  }

  async addItem(): Promise<void> {
    const before = await this.items().count();
    await this.page.locator('#add-item-btn').click();
    await expect(this.items()).toHaveCount(before + 1);
  }

  async addPageBreak(): Promise<void> {
    const before = await this.items().count();
    await this.page.locator('#add-break-btn').click();
    await expect(this.items()).toHaveCount(before + 1);
  }

  async setTitle(index: number, title: string): Promise<void> {
    await this.item(index).locator('.item-title-input').fill(title);
  }

  async setType(index: number, type: string): Promise<void> {
    await this.item(index).locator('.item-type-select').selectOption(type);
  }

  async setDetail(index: number, text: string): Promise<void> {
    await this.item(index).locator('.item-detail-input').fill(text);
  }

  async moveUp(index: number): Promise<void> {
    await this.item(index).locator('[data-action="up"]').click();
  }

  async moveDown(index: number): Promise<void> {
    await this.item(index).locator('[data-action="down"]').click();
  }

  async deleteItem(index: number): Promise<void> {
    const before = await this.items().count();
    await this.item(index).locator('[data-action="delete"]').click();
    await expect(this.items()).toHaveCount(before - 1);
  }
}
