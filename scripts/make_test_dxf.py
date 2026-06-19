"""Создать тестовый DXF для проверки."""
import ezdxf
from skyview.dxf.loader import load_dxf

doc = ezdxf.new("R2010", setup=True)
doc.header["$INSUNITS"] = 4  # mm
msp = doc.modelspace()
msp.add_line((0, 0), (100, 0))
msp.add_line((100, 0), (100, 50))
msp.add_arc((50, 50), 50, 180, 270)
msp.add_circle((25, 25), 10)
blk = doc.blocks.new("HOLE")
blk.add_circle((0, 0), 5)
msp.add_blockref("HOLE", (75, 25))
doc.saveas("test_sample.dxf")

d = load_dxf("test_sample.dxf")
print(f"loaded {len(d.records)} records, units={d.unit_short}")
