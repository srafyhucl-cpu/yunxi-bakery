const FALLBACK_NAV_SPACE_RPX = 112;
const TAB_BAR_SHELL_BOTTOM_RPX = 16;
const TAB_BAR_ISLAND_MIN_HEIGHT_RPX = 112;
const TAB_BAR_TOTAL_HEIGHT_RPX = TAB_BAR_SHELL_BOTTOM_RPX + TAB_BAR_ISLAND_MIN_HEIGHT_RPX;
const TAB_BAR_VISIBLE_CLEARANCE_RPX = 72;
const FIXED_ACTION_EXTRA_SPACE_RPX = 76;

interface MiniappLayoutMetrics {
  pageShellStyle: string;
}

let cachedMetrics: MiniappLayoutMetrics | null = null;

function pxToRpx(px: number, windowWidth: number): number {
  if (!Number.isFinite(px) || px <= 0 || !Number.isFinite(windowWidth) || windowWidth <= 0) {
    return 0;
  }
  return Math.round((px * 750) / windowWidth);
}

function buildPageShellStyle(navSpaceRpx: number, bottomInsetRpx: number): string {
  const tabBarOccupiedHeightRpx = bottomInsetRpx + TAB_BAR_TOTAL_HEIGHT_RPX;
  const pageBottomSpaceRpx = tabBarOccupiedHeightRpx + TAB_BAR_VISIBLE_CLEARANCE_RPX;
  return [
    `--yunxi-custom-nav-space: ${navSpaceRpx}rpx`,
    `--yunxi-page-bottom-space: ${pageBottomSpaceRpx}rpx`,
    `--yunxi-tabbar-occupied-height: ${tabBarOccupiedHeightRpx}rpx`,
    `--yunxi-fixed-action-space: ${pageBottomSpaceRpx + FIXED_ACTION_EXTRA_SPACE_RPX}rpx`,
  ].join("; ");
}

export function getMiniappLayoutMetrics(): MiniappLayoutMetrics {
  if (cachedMetrics) {
    return cachedMetrics;
  }

  try {
    const systemInfo = wx.getSystemInfoSync();
    const windowWidth = systemInfo.windowWidth || systemInfo.screenWidth || 375;
    const statusBarRpx = pxToRpx(systemInfo.statusBarHeight || 0, windowWidth);
    const safeAreaBottomPx = systemInfo.safeArea
      ? Math.max(0, systemInfo.screenHeight - systemInfo.safeArea.bottom)
      : 0;
    const bottomInsetRpx = pxToRpx(safeAreaBottomPx, windowWidth);

    let navSpaceRpx = FALLBACK_NAV_SPACE_RPX;
    if (typeof wx.getMenuButtonBoundingClientRect === "function") {
      const menuButton = wx.getMenuButtonBoundingClientRect();
      const menuBottomRpx = pxToRpx(menuButton.bottom || 0, windowWidth);
      navSpaceRpx = Math.max(menuBottomRpx + 12, statusBarRpx + 44, FALLBACK_NAV_SPACE_RPX);
    } else {
      navSpaceRpx = Math.max(statusBarRpx + 44, FALLBACK_NAV_SPACE_RPX);
    }

    cachedMetrics = {
      pageShellStyle: buildPageShellStyle(navSpaceRpx, bottomInsetRpx),
    };
  } catch {
    cachedMetrics = {
      pageShellStyle: buildPageShellStyle(FALLBACK_NAV_SPACE_RPX, 0),
    };
  }

  return cachedMetrics;
}
