import { getEffectiveFmt as getEffectiveFmtCore, migrateItemType as migrateItemTypeCore } from './modules/formatting-core.js';
import {
  LYRIC_SECTION_RE,
  VERSE_NUM_RE,
  splitLyricsCopyright as splitLyricsCopyrightCore,
  splitLyricSectionIntoStanzas as splitLyricSectionIntoStanzasCore,
  parseSongStanzas as parseSongStanzasCore,
  buildSongDetail as buildSongDetailCore,
  insertSongSeparatorAfter as insertSongSeparatorAfterCore,
  removeSongSeparatorBefore as removeSongSeparatorBeforeCore,
} from './modules/text-core.js';
import { deriveChunkPlan as deriveChunkPlanCore } from './modules/preview-core.js';
import {
  shouldRefreshCalendar as shouldRefreshCalendarCore,
  mergeCalendarEvents as mergeCalendarEventsCore,
  deriveCalendarFetchState as deriveCalendarFetchStateCore,
  deriveCalendarFetchErrorState as deriveCalendarFetchErrorStateCore,
} from './modules/calendar-core.js';
import {
  cloneItemsData as cloneItemsDataCore,
  buildProjectSaveRequest as buildProjectSaveRequestCore,
  deriveProjectSaveSuccess as deriveProjectSaveSuccessCore,
  deriveProjectSaveFailure as deriveProjectSaveFailureCore,
} from './modules/projects-core.js';

Object.assign(globalThis, {
  getEffectiveFmtCore,
  migrateItemTypeCore,
  LYRIC_SECTION_RE,
  VERSE_NUM_RE,
  splitLyricsCopyrightCore,
  splitLyricSectionIntoStanzasCore,
  parseSongStanzasCore,
  buildSongDetailCore,
  insertSongSeparatorAfterCore,
  removeSongSeparatorBeforeCore,
  deriveChunkPlanCore,
  shouldRefreshCalendarCore,
  mergeCalendarEventsCore,
  deriveCalendarFetchStateCore,
  deriveCalendarFetchErrorStateCore,
  cloneItemsDataCore,
  buildProjectSaveRequestCore,
  deriveProjectSaveSuccessCore,
  deriveProjectSaveFailureCore,
});

export const LEGACY_SCRIPT_PATHS = [
  '/src/js/template-registry.js',
  '/src/js/state.js',
  '/src/js/utils.js',
  '/src/js/api.js',
  '/src/js/formatting.js',
  '/src/js/text-renderer.js',
  '/src/js/staff.js',
  '/src/js/editor.js',
  '/src/js/announcements.js',
  '/src/js/calendar.js',
  '/src/js/preview.js',
  '/src/js/songs.js',
  '/src/js/propresenter.js',
  '/src/js/projects.js',
  '/src/js/pco.js',
  '/src/js/update.js',
  '/src/js/templates.js',
  '/src/js/app.js',
];

export function loadLegacyScripts(paths = LEGACY_SCRIPT_PATHS) {
  return paths.reduce((chain, src) => {
    return chain.then(() => {
      return new Promise((resolve, reject) => {
        const existing = document.querySelector(`script[data-legacy-src="${src}"]`);
        if (existing) {
          resolve();
          return;
        }

        const script = document.createElement('script');
        script.src = src;
        script.async = false;
        script.dataset.legacySrc = src;
        script.onload = () => resolve();
        script.onerror = () => reject(new Error(`Failed to load legacy script: ${src}`));
        document.body.appendChild(script);
      });
    });
  }, Promise.resolve());
}

if (typeof document !== 'undefined' && !globalThis.__BG_DISABLE_LEGACY_AUTOLOAD__) {
  loadLegacyScripts().catch(err => {
    console.error(err);
  });
}
