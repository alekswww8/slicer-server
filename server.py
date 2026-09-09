import os
import re
import tempfile
import subprocess
from fastapi import FastAPI, UploadFile, File, Form

app = FastAPI()

def parse_gcode_stats(gcode_path: str):
    weight_g = 0.0
    time_seconds = 0
    with open(gcode_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        m_weight = re.search(r';\s*filament used \[g\]\s*=\s*([0-9.]+)', content)
        if m_weight:
            weight_g = float(m_weight.group(1))
            
        m_time = re.search(r';\s*estimated printing time \(normal mode\)\s*=\s*(.+)', content)
        if m_time:
            time_str = m_time.group(1).strip()
            days = re.search(r'(\d+)d', time_str)
            hours = re.search(r'(\d+)h', time_str)
            minutes = re.search(r'(\d+)m', time_str)
            d = int(days.group(1)) if days else 0
            h = int(hours.group(1)) if hours else 0
            m = int(minutes.group(1)) if minutes else 0
            time_seconds = d * 86400 + h * 3600 + m * 60

    return weight_g, round(time_seconds / 3600.0, 2)

@app.get("/")
def health_check():
    return {"status": "ok", "message": "3D Slicer Server is running"}

@app.post("/slice")
async def slice_stl(
    file: UploadFile = File(...),
    infill: int = Form(15),
    perimeters: int = Form(2)
):
    with tempfile.TemporaryDirectory() as tmpdir:
        input_stl = os.path.join(tmpdir, "model.stl")
        output_gcode = os.path.join(tmpdir, "model.gcode")
        
        content = await file.read()
        with open(input_stl, "wb") as f:
            f.write(content)
            
        cmd = [
            "prusa-slicer",
            "--export-gcode",
            "--layer-height", "0.2",
            "--fill-density", f"{infill}%",
            "--perimeters", str(perimeters),
            "--output", output_gcode,
            input_stl
        ]
        
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if not os.path.exists(output_gcode):
            return {"status": "error", "message": "Сбой нарезки геометрии"}
            
        weight_g, time_h = parse_gcode_stats(output_gcode)
        return {"status": "success", "weight_g": weight_g, "time_hours": time_h}
