Component({
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
  methods: {
    handleAction() {
      this.triggerEvent("action");
    }
  }
});
