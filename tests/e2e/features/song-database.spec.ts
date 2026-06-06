import { test, expect } from '@playwright/test';
import { AppShell } from '../pages/AppShell';
import { SongDbPage } from '../pages/SongDbPage';

test.describe('@core Song Database', () => {
  test('add songs, search/filter, and delete', async ({ page }) => {
    page.on('dialog', (d) => d.accept()); // delete uses native confirm()

    const shell = new AppShell(page);
    await shell.goto();
    await shell.expectAuthenticated();
    await shell.switchTo('songdb');

    const songs = new SongDbPage(page);

    await songs.add('E2E Hymn One', 'Author Alpha', 'Verse one lyrics', 'CCLI 1111');
    await expect(songs.rowByTitle('E2E Hymn One')).toBeVisible();

    await songs.add('E2E Hymn Two', 'Author Beta', 'Verse two lyrics', 'CCLI 2222');
    await expect(songs.rowByTitle('E2E Hymn Two')).toBeVisible();

    // Search narrows the list to the matching song.
    await songs.search().fill('Hymn One');
    await expect(songs.rowByTitle('E2E Hymn One')).toBeVisible();
    await expect(songs.rowByTitle('E2E Hymn Two')).toHaveCount(0);
    await songs.search().fill('');
    await expect(songs.rowByTitle('E2E Hymn Two')).toBeVisible();

    // Delete one; the other remains.
    await songs.deleteByTitle('E2E Hymn One');
    await expect(songs.rowByTitle('E2E Hymn Two')).toBeVisible();
  });
});
