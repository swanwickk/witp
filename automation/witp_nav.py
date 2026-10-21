#!/usr/bin/env python3
"""WitP-AE 地图导航 + 设编队目的地（闭环反馈版）。

关键实测事实（2026-09-28 第十八局标定）：
  1. 顶栏 Hex 必须**单独裁顶栏再 OCR**（全屏 OCR 会丢小字）
  2. 渲染格式为 `Hex112154` —— 无冒号/空格/逗号；末 3 位 = y，其余 = x
  3. 日期渲染为 `May4.1942`（无空格、句点代替逗号）
  4. 点击地图 = 把视野居中到被点格；但 x/y 有耦合（六角格行列偏移）
     实测雅可比（hex/px）≈ [[0.030, 0.028], [0, 0.028]]
  5. 方向键在本局不滚动地图，不依赖它
  6. 点视野中心像素 = 原地重居中 = 无损读数探针
"""
import re
import subprocess
import sys
import time

sys.path.insert(0, '/root/.hermes/profiles/witp/workspace')
sys.path.insert(0, '/root/.hermes/profiles/witp/witp-agent/lib')
import witp_menu as _nav                       # noqa: E402 取窗口偏移
from executor import _game_shot, _ocr          # noqa: E402
from PIL import Image                          # noqa: E402

WS = '/root/.hermes/profiles/witp/workspace'
CENTER = (512, 360)

# ★ 标定（2026-09-28，严格单点法：每次测量前用中心像素重置基准）
#   (+200,0)→+5格  (-200,0)→-5格  (0,+200)→+5格  (0,-200)→-6格
#   (+300,0)→+7格  (0,+300)→+7格
#   ⇒ 两轴均约 40 px/格
PX_X = 40.0
PX_Y = 40.0


# 用户确认：崩溃根因是「点击太快」。节拍必须放宽。
CLICK_DELAY = 6.5     # 每次点击后的静默等待（秒）
KEY_DELAY = 3.0       # 每次按键后的静默等待（秒）


def win_offset():
    """★ 游戏窗口在屏幕上的绝对偏移 —— 点击必须加上它。
    实测窗口在 (188,150)、尺寸 1024x768（不是 0,0）。把窗口坐标当屏幕坐标
    直接注入会整体偏移 188/150 像素，表现为「点了没反应」或「视野乱跳」。"""
    try:
        ox, oy = _nav.offset()
        return int(ox), int(oy)
    except Exception:
        return 0, 0


def click(x, y, action='click'):
    """★ 关键配方（2026-09-28 实测）：点击前必须先做一次**大位移**鼠标移动，
    再移到目标、然后点击。Wine 下鼠标已停在目标位置时不产生 motion 事件，
    游戏会**忽略这次点击** —— 表现为「只有第一次点击有效，之后全失灵」，
    极易误判为「地图冻结」或「点太快」。加入大位移后 4/4 次点击全部生效。"""
    x = max(10, min(1010, int(x)))
    y = max(34, min(700, int(y)))
    ox, oy = win_offset()
    subprocess.run(['python3', f'{WS}/witp_vncclick.py',
                    str(30 + ox), str(730 + oy), 'move'], capture_output=True)
    time.sleep(0.7)
    subprocess.run(['python3', f'{WS}/witp_vncclick.py',
                    str(x + ox), str(y + oy), 'move'], capture_output=True)
    time.sleep(0.9)
    subprocess.run(['python3', f'{WS}/witp_vncclick.py',
                    str(x + ox), str(y + oy), action], capture_output=True)
    time.sleep(CLICK_DELAY)


def key(k):
    subprocess.run(['python3', f'{WS}/witp_vnckey.py', k],
                   capture_output=True)
    time.sleep(KEY_DELAY)


def _crop_ocr(box, scale=4):
    p = f'{WS}/tmp_crop.png'
    im = Image.open(p)
    c = im.crop(box)
    c = c.resize((c.width * scale, c.height * scale))
    q = f'{WS}/tmp_crop_z.png'
    c.save(q)
    return _ocr(q)


def read_topbar():
    """★ 顶栏单独裁剪 OCR。返回 {'date':…, 'hex':(x,y)}"""
    p = f'{WS}/tmp_tb.png'
    ox, oy = win_offset()
    subprocess.run(['bash', '-c',
                    f'DISPLAY=:98 import -window root -crop 1024x768'
                    f'+{ox}+{oy} {p}'], capture_output=True)
    im = Image.open(p)
    im.crop((560, 2, 1024, 24)).resize((1856, 88)).save(f'{WS}/tmp_tb_z.png')
    raw = _ocr(f'{WS}/tmp_tb_z.png')
    out = {'raw': raw.strip(), 'date': None, 'hex': None}
    m = re.search(r'([A-Z][a-z]{2})\s*(\d{1,2})\s*[.,]\s*(\d{4})', raw)
    if m:
        out['date'] = f"{m.group(1)} {m.group(2)}, {m.group(3)}"
    out['hex'] = parse_hex(raw)
    return out


def parse_hex(raw):
    """★ 从顶栏文本解析 Hex 格坐标并**做范围校验**。

    实测（2026-09-28 诊断）：
      · 渲染为无分隔连写：`Hex:98130` → x=98, y=130（Map y 恒为 3 位）
      · 有时尾部图标混进来：`Hex: 981501` → 需要丢掉尾部 1 位才是 98,150
      · **绝不能用「6位拆3+3」的固定规则** —— 会把 98130 拆成 (981,301)。
    正解：取 Hex 后连续数字串，枚举丢弃 0..2 位尾部，取**首个两分量都落在
    合法格范围 (1..200)** 的拆分；y 优先按末 3 位。
    返回 (x, y) 或 None。
    """
    m = re.search(r'[Hh]ex[:\s]*([0-9OoIl][0-9OoIl\s,]{3,12})', raw)
    if not m:
        return None
    d = re.sub(r'[^0-9]', '',
               m.group(1).translate(str.maketrans('OoIl', '0011')))
    for cut in range(0, 3):
        dd = d[:len(d) - cut] if cut else d
        if len(dd) < 4:
            continue
        # 首选：末 3 位为 y（Map 坐标 y 恒 3 位）
        if len(dd) >= 5:
            x, y = int(dd[:-3]), int(dd[-3:])
            if 1 <= x <= 200 and 1 <= y <= 200:
                return (x, y)
        # 次选：len==4 时 2+2
        if len(dd) == 4:
            x, y = int(dd[:2]), int(dd[2:])
            if 1 <= x <= 200 and 1 <= y <= 200:
                return (x, y)
    return None


def ctr(tries=5):
    """
    ★★v19-77 订正：视野中心不能用顶栏 Hex★★
    顶栏 Hex 是**当前选中对象所在格**，不是视野中心：
      · 实测在 TF15 面板开着时，连续读 6 帧恒为 (106,142)
        —— 即 TF15 自己的位置，与视野无关。
      · 故 goto() 看到的"中心"永远是 TF15 的位置，偏差恒定 (-7,+11)，
        且点的像素被钳到 y<=640 ⇒ 视野推不动、原地打转 40 轮。

    正确做法：**开 TF 主面板，点固定锚点像素，读回该像素的格**，
    再由锚点与窗口中心的像素差换算视野中心。
    实测锚点 (287,274) → 稳定读回 (100,139)（6/6 帧一致），
    比例 37.0 px/格（沿单轴逐点实测）。
    这需要 setdest14 的 pick 通道；失败时退回顶栏值（至少不是全错）。
    """
    try:
        import setdest14 as SD
        ANCHOR = (287, 274)          # 偏心锚点（避免落在平移不变点）
        if not SD._enter_pick_mode("TF15", log=None):
            raise RuntimeError("pick 进不去")
        SD._vnc(*ANCHOR)
        import time as _t
        reads = []
        for i in range(5):
            _t.sleep(6.0 if i == 0 else 2.2)
            h = SD._panel_hex(log=None, tag="")
            if h:
                reads.append(h)
        if reads:
            # 取尾连续两次相同
            for i in range(len(reads) - 1, 0, -1):
                if reads[i] == reads[i - 1]:
                    a = reads[i]
                    # 锚点 → 视野中心（窗口中心 512,384）
                    return (a[0] + round((512 - ANCHOR[0]) / 37.0),
                            a[1] + round((384 - ANCHOR[1]) / 37.0))
    except Exception:
        pass
    # 兜底：顶栏（可能是选中对象，仅作最后手段）
    for _ in range(tries):
        h = read_topbar().get('hex')
        if h:
            return h
        time.sleep(0.8)
    return None


def on_map():
    p = f'{WS}/tmp_onmap.png'
    _game_shot(p)
    return 'forecast' in _ocr(p).lower()


def goto(target, max_iter=40, verbose=True):
    """闭环导航：把视野中心格移到 target。"""
    seen = []
    for i in range(max_iter):
        if not on_map():
            key('Escape')
            time.sleep(2)
        c = ctr()
        if c is None:
            if verbose:
                print(f"    轮{i}: 读不到中心 → Esc 复位")
            key('Escape')
            time.sleep(2)
            continue
        dx, dy = target[0] - c[0], target[1] - c[1]
        if verbose:
            print(f"    轮{i}: 中心{c} 偏差({dx:+3d},{dy:+3d})")
        if dx == 0 and dy == 0:
            return True
        if seen.count(c) >= 3:
            if verbose:
                print("    ⚠ 中心停滞 → 微扰")
            click(CENTER[0] + 70, CENTER[1] + 50)
            seen = []
            continue
        seen.append(c)
        # ★ 正确做法：直接算「目标对应的像素」，把它钳到地图可点范围内。
        #   点击是「绝对+幂等」的：点像素 P ⇒ 视野居中到 P 下方的格。
        #   所以每轮都点「目标像素」，残留偏差在下一轮继续收敛。
        #   早先的写法把「格差」钳到 ±3 再算像素 → 每轮算出同一个像素 →
        #   因幂等性原地打转，永远推不出去（已修正）。
        px = CENTER[0] + dx * PX_X
        py = CENTER[1] + dy * PX_Y
        # ★v19-78 钳制放宽★
        #   实测 y=700-720 是「TF15 is at sea」底部提示栏（非地图），
        #   而 y 到 690 仍是地图。原钳制上界 640 使得向南（py>640）
        #   永远被截断 ⇒ 视野推不动。
        #   改为 y∈[120,690]、x∈[130,890]（避开左工具条与底部提示栏）。
        px = max(130, min(890, px))
        py = max(120, min(690, py))
        click(px, py)
    return ctr() == target


TF_ROW_Y = {'TF14': 251, 'TF15': 265, 'TF16': 279,
            'TF17': 293, 'TF18': 307, 'TF20': 321}


def open_tf_list():
    """★ 只按键，绝不点地图 —— 点地图会把视野居中移走，导致随后
    「点视野中心像素」落子落错格。"""
    key('t')
    time.sleep(3.0)
    p = f'{WS}/tmp_tfl.png'
    _game_shot(p)
    return 'endure' in _ocr(p).lower()


def set_dest(tf, target):
    """把 TF 的目的地设为 target（先把视野居中到 target，再点中心像素）。"""
    print(f"  [{tf}] 目标 {target}")
    if not goto(target):
        print(f"  [{tf}] ✗ 导航失败，放弃")
        return False
    if not open_tf_list():
        print(f"  [{tf}] ✗ 打不开 T 列表")
        return False
    row = TF_ROW_Y.get(tf)
    print(f"  [{tf}] 双击行 y={row}")
    click(200, row, 'dblclick')
    time.sleep(4)
    click(534, 204)          # 目的地字段 → 拾取模式
    time.sleep(2.5)
    click(CENTER[0], CENTER[1])   # 点视野中心 = 目标格
    time.sleep(2.5)
    key('Escape')
    time.sleep(2)
    return True


if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'ctr':
        print(read_topbar())
    elif mode == 'goto':
        print("到达:", goto((int(sys.argv[2]), int(sys.argv[3]))))
    elif mode == 'set':
        print(set_dest(sys.argv[2], (int(sys.argv[3]), int(sys.argv[4]))))
