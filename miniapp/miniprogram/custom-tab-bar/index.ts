import { TAB_BAR_ITEMS } from "../constants/tab-bar";

Component({
  data: {
    selected: 0,
    items: TAB_BAR_ITEMS
  },
  methods: {
    switchTab(event: WechatMiniprogram.TouchEvent) {
      const index = Number(event.currentTarget.dataset.index || 0);
      const item = TAB_BAR_ITEMS[index];
      if (!item) {
        return;
      }
      if (this.data.selected !== index) {
        this.setData({ selected: index });
      }
      wx.switchTab({ url: item.pagePath });
    }
  }
});
