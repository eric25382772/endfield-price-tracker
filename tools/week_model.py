"""本週買價鎖定：8 模板 × 個人偏移值（ε）擬合。

遊戲的彈性物資價格不是隨機的：

    價格[星期幾] = 模板基準[星期幾] × (1 + 模板係數 × ε[星期幾])

每週由系統隨機抽一個模板（共 8 種），但 ε 是每帳號 × 每物品 × 每星期幾固定不變的。
所以只要用歷史資料反推出 ε，本週掃到幾天就能反推是哪個模板，整週價格隨之確定。

週一的 8 個模板會塌成 6 種價格（⑤⑥ 與 ⑦⑧ 各自同值同係數），
所以掃完週一通常只剩 1~2 個候選，掃完週二必定唯一。

模板數字來源：第三方分析儀 https://endpa.netlify.app 的原始碼，
已用本專案 data/prices.db 的 449 個完整週驗證，吻合 92.4%。

跨週不適用：下週一會重新抽模板，所以只鎖定「本週」。
"""
from datetime import date, timedelta

# (週一..週日 的基準值, 係數)
TEMPLATES = [
    ('逐漸上升', (1600, 2000, 2200, 2600, 3000, 3200, 3400), 5),
    ('逐漸下降', (2200, 2000, 1800, 1700, 1500, 1200, 1100), 5),
    ('先降後升', (2400, 2000, 1600, 1400, 1600, 2000, 2200), 5),
    ('先升後降', (1800, 2000, 2600, 3000, 3400, 2600, 2000), 5),
    ('奇高小震', (2000, 1600, 2400, 1600, 2400, 1600, 2400), 4),
    ('偶高小震', (2000, 2400, 1600, 2400, 1600, 2400, 1600), 4),
    ('奇高大震', (2200, 1400, 3000, 1200, 3600, 1000, 4000), 6),
    ('偶高大震', (2200, 3000, 1600, 3600, 1200, 4000, 1000), 6),
]

MIN_WEEK_DAYS = 3      # 一週至少看到幾天才拿來推 ε
MIN_CLEAN_WEEKS = 2    # 至少幾個過去週對得上才信這組 ε
TOL_ABS = 2            # 允許的取整誤差
TOL_REL = 0.0008


def _tol(price):
    return max(TOL_ABS, TOL_REL * abs(price))


def _monday(d):
    return d - timedelta(days=d.weekday())


def _split_weeks(series):
    """[(game_date, price)] → {週一日期: [7 格價格]}"""
    weeks = {}
    for ds, price in series:
        d = date.fromisoformat(ds)
        slots = weeks.setdefault(_monday(d), [None] * 7)
        slots[d.weekday()] = price
    return weeks


def _day_ok(raw, actual, lo, hi):
    """算出來的 raw 和實際值對得上嗎（含撞到價格上下限的情況）"""
    p = round(raw)
    if abs(p - actual) <= _tol(actual):
        return True
    if lo is not None and p < lo and abs(actual - lo) <= _tol(actual):
        return True
    if hi is not None and p > hi and abs(actual - hi) <= _tol(actual):
        return True
    return False


def _fits(eps, prices, lo, hi):
    """這組 ε 下，有沒有某個模板能解釋這一週？回傳該模板或 None。

    ε 還不知道的那幾天（該星期幾從沒掃到過）直接跳過不檢查 —— 無從驗證，
    不是「對不上」。整組放棄的話，像剛上架、只掃過半週的物品會永遠推不出來。
    """
    for tpl in TEMPLATES:
        _, grid, coeff = tpl
        ok = True
        for i, actual in enumerate(prices):
            if actual is None or eps[i] is None:
                continue
            if not _day_ok(grid[i] * (1 + coeff * eps[i]), actual, lo, hi):
                ok = False
                break
        if ok:
            return tpl
    return None


def _eps_from(prices, grid, coeff):
    return [None if p is None else (p / grid[i] - 1) / coeff
            for i, p in enumerate(prices)]


def _solve_epsilon(past_weeks, lo, hi):
    """從過去的週推出 ε。回傳 (eps, 對得上的週數)。"""
    best_eps, best_clean = None, []
    for src in past_weeks:
        for _, grid, coeff in TEMPLATES:
            eps = _eps_from(src, grid, coeff)
            clean = [(w, hit) for w in past_weeks
                     if (hit := _fits(eps, w, lo, hi)) is not None]
            if best_eps is None or len(clean) > len(best_clean):
                best_eps, best_clean = eps, clean
    if best_eps is None:
        return None, 0

    # 精修：取「可行區間的交集」而不是加權平均。
    # 遊戲存的是整數，所以觀測到 p 代表 p-0.5 <= 基準×(1+係數×ε) < p+0.5，
    # 每筆觀測都把 ε 夾在一個區間裡；交集的中點能讓每個觀測日都算回原值，
    # 沒看過的日子也會落在最準的位置。取平均會有 ±1 的取整誤差，交集不會。
    # 撞到價格上下限的那幾天只給「單邊」的界線：被天花板削平代表原始值至少有那麼高，
    # 所以只能拉高 ε 的下界，不能當等式用（反過來地板同理）。
    # 不這樣做的話，常撞天花板的物品 ε 會被低估，預測值會差 1。
    refined = list(best_eps)
    for i in range(7):
        low = float('-inf')
        high = float('inf')
        seen = False
        for prices, (_, grid, coeff) in best_clean:
            p = prices[i]
            if p is None:
                continue
            seen = True
            if p != lo:
                low = max(low, ((p - 0.5) / grid[i] - 1) / coeff)
            if p != hi:
                high = min(high, ((p + 0.5) / grid[i] - 1) / coeff)
        if seen and low <= high and low != float('-inf') and high != float('inf'):
            refined[i] = (low + high) / 2
    return refined, len(best_clean)


def lock_week(series, today, lo=None, hi=None):
    """反推本週買價。

    series: [(game_date, price)]，該物品的我方歷史價（遞增）
    today:  'YYYY-MM-DD' 遊戲日
    lo/hi:  該物品的價格上下限（傳 None 會用歷史極值）

    回傳 dict：
        locked        本週模板是否唯一確定
        week_prices   [7] 週一..週日的買價；已過的日子用實際值，
                      未到的日子在 locked 時是算出來的，否則為 None
        today_index   今天是星期幾（0=週一）
        rest_min      今天到週日之間的最低買價（locked 時才有）
        rest_min_offset  最低價在幾天後（0=今天）
        candidates    還剩幾個模板候選
    """
    today_d = date.fromisoformat(today)
    blank = {'locked': False, 'week_prices': None, 'today_index': today_d.weekday(),
             'rest_min': None, 'rest_min_offset': None, 'candidates': len(TEMPLATES)}
    if not series:
        return blank

    prices_all = [p for _, p in series]
    if lo is None:
        lo = min(prices_all)
    if hi is None:
        hi = max(prices_all)

    weeks = _split_weeks(series)
    this_monday = _monday(today_d)
    current = weeks.get(this_monday, [None] * 7)
    past = [slots for monday, slots in weeks.items()
            if monday != this_monday and sum(x is not None for x in slots) >= MIN_WEEK_DAYS]
    if len(past) < MIN_CLEAN_WEEKS:
        return blank

    eps, clean_count = _solve_epsilon(past, lo, hi)
    if eps is None or clean_count < MIN_CLEAN_WEEKS:
        return blank

    # 用本週已經看到的日子篩掉對不上的模板（ε 還不知道的那幾天跳過）
    pool = []
    for tpl in TEMPLATES:
        _, grid, coeff = tpl
        if all(actual is None or eps[i] is None
               or _day_ok(grid[i] * (1 + coeff * eps[i]), actual, lo, hi)
               for i, actual in enumerate(current)):
            pool.append(tpl)

    result = dict(blank, candidates=len(pool))
    if len(pool) != 1:
        return result

    # 本週剩下的每一天都要算得出來（已經掃到 或 ε 已知）才算鎖定。
    # 缺一天就講不出「哪天最便宜」，寧可說不知道。
    idx = today_d.weekday()
    if any(current[i] is None and eps[i] is None for i in range(idx, 7)):
        return result

    _, grid, coeff = pool[0]
    week_prices = [
        current[i] if current[i] is not None
        else (None if eps[i] is None
              else min(hi, max(lo, round(grid[i] * (1 + coeff * eps[i])))))
        for i in range(7)
    ]
    rest = week_prices[idx:]
    result.update(locked=True, week_prices=week_prices,
                  rest_min=min(rest), rest_min_offset=rest.index(min(rest)))
    return result
