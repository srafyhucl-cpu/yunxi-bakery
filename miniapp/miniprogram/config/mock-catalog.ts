import type { CatalogCategory, CatalogProduct } from "../types/catalog";

export const CATALOG_CATEGORIES: CatalogCategory[] = [
  { id: "birthday-cake", title: "生日蛋糕", iconText: "蛋糕" },
  { id: "dessert-bread", title: "甜品&面包", iconText: "面包" },
  { id: "cookies", title: "饼干&糕点", iconText: "饼干" },
  { id: "tea-food", title: "茶饮堂食甜品", iconText: "茶饮" }
];

export const CATALOG_PRODUCTS: CatalogProduct[] = [
  {
    id: "p_001",
    title: "父亲节健康蛋糕",
    subtitle: "平凡爸爸，是我心中第一名",
    imageUrl: "https://images.unsplash.com/photo-1578985545062-69928b1d9587?w=600&auto=format&fit=crop&q=80",
    priceFen: 23800,
    soldText: "本店人气榜第1",
    categoryId: "birthday-cake",
    stock: 12,
    isActive: true,
    tags: ["父亲节", "健康"],
    description: "清爽奶油与低甜配方，适合家庭聚会。",
    specs: ["6寸", "8寸", "10寸"],
    notices: ["需提前24小时预订", "装饰插件不可食用"]
  },
  {
    id: "p_002",
    title: "巧克力奥利奥千层",
    subtitle: "浓郁巧克力与奥利奥夹心",
    imageUrl: "https://images.unsplash.com/photo-1535141192574-5d4897c13636?w=600&auto=format&fit=crop&q=80",
    priceFen: 24800,
    soldText: "近期热卖",
    categoryId: "birthday-cake",
    stock: 8,
    isActive: true,
    tags: ["热卖", "千层"],
    description: "层层薄饼搭配巧克力奶油，口感绵密。",
    specs: ["6寸", "8寸"],
    notices: ["冷藏保存", "建议2小时内食用"]
  },
  {
    id: "p_003",
    title: "蜂蜜无水老蛋糕（一盒6个）",
    subtitle: "经典老式蛋糕",
    imageUrl: "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=600&auto=format&fit=crop&q=80",
    priceFen: 1000,
    soldText: "本店人气榜第8",
    categoryId: "dessert-bread",
    stock: 30,
    isActive: true,
    tags: ["招牌", "面包"],
    description: "无水工艺制作，蜂蜜香气明显。",
    specs: ["一盒6个"],
    notices: ["当日现烤", "常温保存"]
  },
  {
    id: "p_004",
    title: "餐具（5人份）",
    subtitle: "一次性生日餐具",
    imageUrl: "https://images.unsplash.com/photo-1543510473-ac2c353edd9e?w=600&auto=format&fit=crop&q=80",
    priceFen: 500,
    soldText: "常用加购",
    categoryId: "tea-food",
    stock: 100,
    isActive: true,
    tags: ["餐具"],
    description: "包含餐盘、叉子与蛋糕刀。",
    specs: ["5人份"],
    notices: ["可随蛋糕一起配送"]
  },
  {
    id: "p_005",
    title: "抹茶树莓巧克力蛋糕",
    subtitle: "清新抹茶与树莓果香",
    imageUrl: "https://images.unsplash.com/photo-1582231375626-1417e85cb511?w=600&auto=format&fit=crop&q=80",
    priceFen: 13800,
    soldText: "新品",
    categoryId: "birthday-cake",
    stock: 6,
    isActive: true,
    tags: ["新品", "水果"],
    description: "抹茶奶油搭配树莓酸甜口感。",
    specs: ["4寸", "6寸"],
    notices: ["水果装饰随季节调整"]
  },
  {
    id: "p_006",
    title: "原料展示：安佳淡奶油",
    subtitle: "烘焙原料展示，不单独售卖",
    imageUrl: "https://images.unsplash.com/photo-1550583724-b2692b85b150?w=600&auto=format&fit=crop&q=80",
    priceFen: 0,
    soldText: "原料展示",
    categoryId: "cookies",
    stock: 0,
    isActive: true,
    tags: ["原料"],
    description: "用于展示门店常用原料。",
    specs: ["展示项"],
    notices: ["非售卖商品"]
  }
];

