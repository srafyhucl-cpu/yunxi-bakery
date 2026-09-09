Component({
  options: {
    styleIsolation: "apply-shared",
  },
  properties: {
    statusText: {
      type: String,
      value: ""
    },
    badgeText: {
      type: String,
      value: ""
    },
    description: {
      type: String,
      value: ""
    },
    actionText: {
      type: String,
      value: ""
    },
    iconText: {
      type: String,
      value: "登"
    }
  },
  data: {
    hasAction: false,
    actionLabel: ""
  },
  observers: {
    actionText(value: string) {
      const actionLabel = String(value || "").trim();
      this.setData({
        hasAction: actionLabel.length > 0,
        actionLabel
      });
    }
  },
  methods: {
    handleAction() {
      this.triggerEvent("action");
    }
  }
});
