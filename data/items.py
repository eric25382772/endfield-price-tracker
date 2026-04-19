# 彈性物資清單 (Elastic Goods)
# 已根據遊戲實際 UI 校正 (2026-04-05)
# base_price 為基準價 2000

# 四號谷地地區物品 (Valley IV) - 每日購買配額 +320，上限 960（3天滿）
VALLEY_IV_GOODS = [
    {"name_cn": "錨點廚具貨組", "name_en": "Anchor Kitchenware", "base_price": 2000, "region": "valley_iv"},
    {"name_cn": "懸空嶽獸骨雕貨組", "name_en": "Floating Beast Bone Carving", "base_price": 2000, "region": "valley_iv"},
    {"name_cn": "巫術礦鑽貨組", "name_en": "Witchcraft Mining Drill", "base_price": 2000, "region": "valley_iv"},
    {"name_cn": "天使罐頭貨組", "name_en": "Angel Canned Food", "base_price": 2000, "region": "valley_iv"},
    {"name_cn": "谷地水培肉貨組", "name_en": "Valley Hydro Meat", "base_price": 2000, "region": "valley_iv"},
    {"name_cn": "團結牌口服液貨組", "name_en": "Unity Oral Liquid", "base_price": 2000, "region": "valley_iv"},
    {"name_cn": "源石樹幼苗貨組", "name_en": "Originium Saplings", "base_price": 2000, "region": "valley_iv"},
    {"name_cn": "塞什卡髀石貨組", "name_en": "Seshka Knucklebones", "base_price": 2000, "region": "valley_iv"},
    {"name_cn": "警戒者礦鎬貨組", "name_en": "Vigilant Pickaxes", "base_price": 2000, "region": "valley_iv"},
    {"name_cn": "星體晶塊貨組", "name_en": "Astral Crystal", "base_price": 2000, "region": "valley_iv"},
    {"name_cn": "碎料積木貨組", "name_en": "Scrap Toy Blocks", "base_price": 2000, "region": "valley_iv"},
    {"name_cn": "硬頭殼安全帽貨組", "name_en": "Hard Shell Helmet", "base_price": 2000, "region": "valley_iv"},
]

# 武陵地區物品 (Wuling) - 每日購買配額 +125，上限 250（2天滿）
WULING_GOODS = [
    {"name_cn": "武俠電影貨組", "name_en": "Wuxia Movies", "base_price": 2000, "region": "wuling"},
    {"name_cn": "冬蟲夏筍貨組", "name_en": "Cordyceps Bamboo Shoots", "base_price": 2000, "region": "wuling"},
    {"name_cn": "武陵凍梨貨組", "name_en": "Wuling Frozen Pears", "base_price": 2000, "region": "wuling"},
    {"name_cn": "岳研避瘴茶貨組", "name_en": "Yue Anti-miasma Tea", "base_price": 2000, "region": "wuling"},
    {"name_cn": "天師龍泡泡貨組", "name_en": "Celestial Dragon Bubbles", "base_price": 2000, "region": "wuling"},
    {"name_cn": "息壤淨水濾心貨組", "name_en": "Xirang Water Filter Pack", "base_price": 2000, "region": "wuling"},
    {"name_cn": "清波筏貨組", "name_en": "Qingbo Raft Pack", "base_price": 2000, "region": "wuling"},
]

# 全部物品
ELASTIC_GOODS = VALLEY_IV_GOODS + WULING_GOODS

# 購買配額設定
REGION_QUOTA = {
    'valley_iv': {'daily': 320, 'max': 960, 'fill_days': 3},
    'wuling': {'daily': 125, 'max': 250, 'fill_days': 2},
}


def get_all_item_names_cn():
    """Return list of all Chinese item names for OCR matching."""
    return [item["name_cn"] for item in ELASTIC_GOODS]


def get_items_by_region(region):
    """Return items for a specific region."""
    return [item for item in ELASTIC_GOODS if item.get("region") == region]
