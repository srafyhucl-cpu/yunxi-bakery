-- 迁移 v049：商品图片本地化
--
-- 背景：商品图片目前直接引用有赞 CDN（img.yzcdn.cn）。停止有赞后这些地址会全部失效，
-- 小程序商品页会整页裂图。新增 image_local 保存服务器本地图片的相对路径，
-- 为空时继续回退远程图片，保证迁移过程可灰度、可回滚。
--
-- 说明：字段默认空串，历史数据无需回填；由同步脚本逐条下载并写入。

ALTER TABLE youzan_products ADD COLUMN image_local TEXT NOT NULL DEFAULT '';
