"""Build the M10-style 200 x 150 mm plastic car shell in Rhino 8.

Run inside Rhino CPython through RhinoMCP's
execute_rhinoscript_python_code tool. Units are millimetres.
"""

import math
import os

import Rhino
import scriptcontext as sc
import rhinoscriptsyntax as rs
import System
from System.Drawing import Color


DOC = sc.doc
TOL = max(DOC.ModelAbsoluteTolerance, 0.01)
OUTPUT_3DM = os.environ.get("M10_CAD_OUTPUT", os.path.abspath("M10_shell_200x150mm.3dm"))


COLORS = {
    "white": Color.FromArgb(248, 248, 246),
    "white_alt": Color.FromArgb(226, 230, 232),
    "black": Color.FromArgb(12, 15, 18),
    "cyan": Color.FromArgb(0, 205, 255),
    "silver": Color.FromArgb(174, 183, 190),
    "pink": Color.FromArgb(255, 150, 166),
    "gray": Color.FromArgb(105, 112, 118),
    "pcb": Color.FromArgb(33, 122, 82),
}


LAYERS = {
    "reference": ("M10_00_REFERENCE", Color.FromArgb(110, 110, 110)),
    "chassis": ("M10_01_NESTING_CHASSIS", COLORS["white_alt"]),
    "shell": ("M10_02_PLASTIC_SHELL", COLORS["white"]),
    "display": ("M10_03_SCREEN_RECESS", COLORS["black"]),
    "graphics": ("M10_04_FACE_GRAPHICS", COLORS["white"]),
    "sensors": ("M10_05_SENSORS", COLORS["cyan"]),
    "hardware": ("M10_06_MOUNTING_HARDWARE", COLORS["silver"]),
    "rear": ("M10_07_REAR_HATCH", COLORS["white_alt"]),
    "electronics": ("M10_08_ELECTRONICS_REFERENCE", COLORS["pcb"]),
}


def ensure_layer(name, color):
    index = DOC.Layers.FindByFullPath(name, -1)
    if index < 0:
        layer = Rhino.DocObjects.Layer()
        layer.Name = name
        layer.Color = color
        index = DOC.Layers.Add(layer)
    return index


LAYER_INDEX = {key: ensure_layer(*value) for key, value in LAYERS.items()}


def clear_previous_m10_geometry():
    doomed = []
    settings = Rhino.DocObjects.ObjectEnumeratorSettings()
    settings.NormalObjects = True
    settings.HiddenObjects = True
    settings.LockedObjects = True
    for obj in DOC.Objects.GetObjectList(settings):
        layer = DOC.Layers[obj.Attributes.LayerIndex]
        if layer and layer.FullPath.startswith("M10_"):
            doomed.append(obj.Id)
    for object_id in doomed:
        DOC.Objects.Delete(object_id, True)
    return len(doomed)


def attributes(layer_key, name, color=None):
    attr = Rhino.DocObjects.ObjectAttributes()
    attr.LayerIndex = LAYER_INDEX[layer_key]
    attr.Name = name
    attr.WireDensity = -1
    if color is not None:
        attr.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
        attr.ObjectColor = color
    return attr


def add_brep(brep, layer_key, name, color=None):
    if brep is None:
        raise RuntimeError("No Brep produced for %s" % name)
    object_id = DOC.Objects.AddBrep(brep, attributes(layer_key, name, color))
    if object_id == System.Guid.Empty:
        raise RuntimeError("Could not add Brep: %s" % name)
    return object_id


def add_curve(curve, layer_key, name, color=None):
    object_id = DOC.Objects.AddCurve(curve, attributes(layer_key, name, color))
    if object_id == System.Guid.Empty:
        raise RuntimeError("Could not add curve: %s" % name)
    return object_id


def superellipse_xy(z, length, width, exponent=4.0, samples=64):
    points = []
    a = length * 0.5
    b = width * 0.5
    power = 2.0 / exponent
    for i in range(samples):
        angle = 2.0 * math.pi * i / samples
        c = math.cos(angle)
        s = math.sin(angle)
        x = a * math.copysign(abs(c) ** power, c)
        y = b * math.copysign(abs(s) ** power, s)
        points.append(Rhino.Geometry.Point3d(x, y, z))
    curve = Rhino.Geometry.NurbsCurve.Create(True, 3, points)
    bbox = curve.GetBoundingBox(True)
    scale = Rhino.Geometry.Transform.Scale(
        Rhino.Geometry.Plane.WorldXY,
        length / bbox.Diagonal.X,
        width / bbox.Diagonal.Y,
        1.0,
    )
    curve.Transform(scale)
    return curve


def superellipse_yz(x, center_y, center_z, width, height, exponent=4.0, samples=64):
    points = []
    a = width * 0.5
    b = height * 0.5
    power = 2.0 / exponent
    for i in range(samples):
        angle = 2.0 * math.pi * i / samples
        c = math.cos(angle)
        s = math.sin(angle)
        y = center_y + a * math.copysign(abs(c) ** power, c)
        z = center_z + b * math.copysign(abs(s) ** power, s)
        points.append(Rhino.Geometry.Point3d(x, y, z))
    curve = Rhino.Geometry.NurbsCurve.Create(True, 3, points)
    bbox = curve.GetBoundingBox(True)
    plane = Rhino.Geometry.Plane(
        Rhino.Geometry.Point3d(x, center_y, center_z),
        Rhino.Geometry.Vector3d.YAxis,
        Rhino.Geometry.Vector3d.ZAxis,
    )
    scale = Rhino.Geometry.Transform.Scale(
        plane,
        width / bbox.Diagonal.Y,
        height / bbox.Diagonal.Z,
        1.0,
    )
    curve.Transform(scale)
    return curve


def orient_outward(brep):
    if brep and brep.IsSolid and brep.SolidOrientation == Rhino.Geometry.BrepSolidOrientation.Inward:
        brep.Flip()
    return brep


def capped_loft(curves, loft_type=Rhino.Geometry.LoftType.Normal):
    lofts = Rhino.Geometry.Brep.CreateFromLoft(
        curves,
        Rhino.Geometry.Point3d.Unset,
        Rhino.Geometry.Point3d.Unset,
        loft_type,
        False,
    )
    if not lofts:
        raise RuntimeError("Loft failed")
    capped = lofts[0].CapPlanarHoles(TOL)
    if capped is None:
        raise RuntimeError("CapPlanarHoles failed")
    return orient_outward(capped)


def prism_xy(z0, z1, length, width, exponent=4.0):
    return capped_loft(
        [
            superellipse_xy(z0, length, width, exponent),
            superellipse_xy(z1, length, width, exponent),
        ],
        Rhino.Geometry.LoftType.Straight,
    )


def prism_yz(x0, x1, center_y, center_z, width, height, exponent=4.0):
    return capped_loft(
        [
            superellipse_yz(x0, center_y, center_z, width, height, exponent),
            superellipse_yz(x1, center_y, center_z, width, height, exponent),
        ],
        Rhino.Geometry.LoftType.Straight,
    )


def cylinder(base, axis, height, radius):
    normal = Rhino.Geometry.Vector3d(axis)
    normal.Unitize()
    plane = Rhino.Geometry.Plane(base, normal)
    circle = Rhino.Geometry.Circle(plane, radius)
    return orient_outward(Rhino.Geometry.Cylinder(circle, height).ToBrep(True, True))


def boolean_difference(targets, cutters, label):
    result = Rhino.Geometry.Brep.CreateBooleanDifference(targets, cutters, TOL)
    if not result:
        raise RuntimeError("Boolean difference failed: %s" % label)
    return [orient_outward(brep) for brep in result]


def boolean_union(breps, label):
    result = Rhino.Geometry.Brep.CreateBooleanUnion(breps, TOL)
    if not result:
        raise RuntimeError("Boolean union failed: %s" % label)
    return list(result)


def ring(base, axis, depth, outer_radius, inner_radius):
    outer = cylinder(base, axis, depth, outer_radius)
    inner_base = Rhino.Geometry.Point3d(base)
    direction = Rhino.Geometry.Vector3d(axis)
    direction.Unitize()
    inner_base -= direction * 0.2
    inner = cylinder(inner_base, direction, depth + 0.4, inner_radius)
    return boolean_difference([outer], [inner], "ring")[0]


def add_text(text, origin, x_axis, y_axis, height, layer_key, name, color):
    entity = Rhino.Geometry.TextEntity()
    entity.PlainText = text
    entity.Plane = Rhino.Geometry.Plane(origin, x_axis, y_axis)
    entity.TextHeight = height
    object_id = DOC.Objects.AddText(entity, attributes(layer_key, name, color))
    if object_id == System.Guid.Empty:
        raise RuntimeError("Could not add text: %s" % text)
    return object_id


deleted_count = clear_previous_m10_geometry()
rs.UnitSystem(2, False, True)
DOC.ModelAbsoluteTolerance = 0.01
DOC.ModelAngleToleranceRadians = math.radians(1.0)


# 1. Main injection-moulded body. The lowest outer section is exactly
#    200 x 150 mm, matching the requested 20 x 15 cm footprint.
outer_sections = [
    superellipse_xy(8.0, 200.0, 150.0, 2.0),
    superellipse_xy(30.0, 202.0, 152.0, 2.35),
    superellipse_xy(62.0, 202.0, 152.0, 3.2),
    superellipse_xy(88.0, 200.0, 151.0, 4.0),
    superellipse_xy(126.0, 184.0, 142.0, 4.1),
    superellipse_xy(152.0, 151.0, 122.0, 3.7),
    superellipse_xy(170.0, 112.0, 94.0, 3.2),
]
inner_sections = [
    superellipse_xy(0.0, 193.0, 143.0, 2.0),
    superellipse_xy(30.0, 195.0, 145.0, 2.35),
    superellipse_xy(62.0, 195.0, 145.0, 3.2),
    superellipse_xy(88.0, 193.0, 144.0, 4.0),
    superellipse_xy(126.0, 177.0, 135.0, 4.1),
    superellipse_xy(150.0, 144.0, 115.0, 3.7),
    superellipse_xy(164.0, 105.0, 87.0, 3.2),
]
outer_body = capped_loft(outer_sections)
inner_void = capped_loft(inner_sections)
shell_parts = boolean_difference([outer_body], [inner_void], "hollow plastic shell")

# True screen opening: 76 x 46 mm gives a 75 x 45 mm module 0.5 mm
# clearance on each edge. It passes through the front shell into the interior.
screen_opening = prism_yz(-110.0, -86.0, 0.0, 118.0, 76.0, 46.0, 3.8)
shell_parts = boolean_difference(shell_parts, [screen_opening], "75x45 screen opening")
for index, part in enumerate(shell_parts):
    add_brep(part, "shell", "M10_MAIN_SHELL_%02d" % (index + 1), COLORS["white"])


# 2. Flat elliptical nesting chassis. The shell opening is 193 x 143 mm;
#    the 192 x 142 mm tray therefore has 0.5 mm clearance per side.
chassis = prism_xy(1.5, 6.0, 192.0, 142.0, 2.0)
add_brep(chassis, "chassis", "CHASSIS_TRAY_INSERT_192x142", COLORS["white_alt"])

locating_outer = prism_xy(6.0, 12.0, 188.0, 138.0, 2.0)
locating_inner = prism_xy(5.5, 12.5, 180.0, 130.0, 2.0)
locating_ring = boolean_difference([locating_outer], [locating_inner], "chassis locating lip")[0]
add_brep(locating_ring, "chassis", "CHASSIS_ELLIPTICAL_LOCATING_LIP", COLORS["white_alt"])


# 3. Internal screw bosses for electronics plate mounting.
for x in (-52.0, 52.0):
    for y in (-38.0, 38.0):
        boss = ring(
            Rhino.Geometry.Point3d(x, y, 6.0),
            Rhino.Geometry.Vector3d.ZAxis,
            18.0,
            5.5,
            2.15,
        )
        add_brep(boss, "hardware", "MOUNT_BOSS_%+.0f_%+.0f" % (x, y), COLORS["white_alt"])


# 4. Recessed 75 x 45 mm screen, rear carrier, mainboard and cable path.
#    The screen and PCB are reference envelopes so their unconfirmed thicknesses
#    remain easy to edit without changing the shell surface.
bezel_outer = prism_yz(-95.0, -91.0, 0.0, 118.0, 84.0, 54.0, 3.8)
bezel_inner = prism_yz(-95.5, -90.5, 0.0, 118.0, 76.0, 46.0, 3.8)
screen_bezel = boolean_difference([bezel_outer], [bezel_inner], "screen recess bezel")[0]
add_brep(screen_bezel, "shell", "SCREEN_RECESSED_BEZEL_84x54", COLORS["white_alt"])

screen_module = prism_yz(-91.0, -87.0, 0.0, 118.0, 75.0, 45.0, 3.6)
add_brep(screen_module, "display", "SCREEN_MODULE_REFERENCE_75x45x4", COLORS["black"])

pcb = prism_yz(-80.0, -78.0, 0.0, 118.0, 90.0, 60.0, 3.4)
cable_slot = prism_yz(-81.0, -77.0, 0.0, 94.0, 24.0, 8.0, 3.4)
pcb_parts = boolean_difference([pcb], [cable_slot], "mainboard cable routing slot")
for index, part in enumerate(pcb_parts):
    add_brep(part, "electronics", "MAINBOARD_REFERENCE_90x60_%02d" % (index + 1), COLORS["pcb"])

screen_axis = Rhino.Geometry.Vector3d.XAxis
for y in (-38.0, 38.0):
    for z in (94.0, 142.0):
        standoff = ring(
            Rhino.Geometry.Point3d(-90.0, y, z), screen_axis, 10.0, 3.5, 1.4
        )
        add_brep(standoff, "hardware", "SCREEN_PCB_STANDOFF", COLORS["silver"])

cable_frame_outer = prism_yz(-87.0, -80.0, 0.0, 91.0, 28.0, 12.0, 3.2)
cable_frame_inner = prism_yz(-87.5, -79.5, 0.0, 91.0, 24.0, 8.0, 3.2)
cable_frame = boolean_difference(
    [cable_frame_outer], [cable_frame_inner], "screen cable guide"
)[0]
add_brep(cable_frame, "hardware", "SCREEN_CABLE_GUIDE_24x8", COLORS["silver"])

front_axis = Rhino.Geometry.Vector3d(-1.0, 0.0, 0.0)
camera_outer = cylinder(Rhino.Geometry.Point3d(-95.0, 0.0, 149.0), front_axis, 3.0, 6.2)
camera_lens = cylinder(Rhino.Geometry.Point3d(-98.1, 0.0, 149.0), front_axis, 1.0, 2.8)
add_brep(camera_outer, "display", "FRONT_CAMERA_HOUSING", COLORS["black"])
add_brep(camera_lens, "sensors", "FRONT_CAMERA_LENS", COLORS["cyan"])

front_led = prism_yz(-102.0, -103.5, 0.0, 52.0, 94.0, 6.0, 4.2)
add_brep(front_led, "sensors", "FRONT_LED_BAR", COLORS["cyan"])

add_text(
    "M10",
    Rhino.Geometry.Point3d(-102.4, 14.5, 72.0),
    Rhino.Geometry.Vector3d(0.0, -1.0, 0.0),
    Rhino.Geometry.Vector3d(0.0, 0.0, 1.0),
    11.0,
    "graphics",
    "M10_LABEL",
    COLORS["gray"],
)


# 5. Top lidar / status puck, matching the cyan ring in the references.
top_stack = [
    (168.0, 6.0, 28.0, COLORS["white_alt"], "TOP_SENSOR_BASE"),
    (174.0, 4.0, 24.0, COLORS["silver"], "TOP_SENSOR_TRIM"),
    (178.0, 3.0, 20.0, COLORS["black"], "TOP_SENSOR_BLACK_RING"),
    (181.0, 2.0, 14.5, COLORS["cyan"], "TOP_SENSOR_LENS"),
]
for z, height, radius, color, name in top_stack:
    puck = cylinder(Rhino.Geometry.Point3d(0.0, 0.0, z), Rhino.Geometry.Vector3d.ZAxis, height, radius)
    add_brep(puck, "sensors", name, color)


# 6. Symmetric side proximity sensor rings.
for y, direction in ((75.0, Rhino.Geometry.Vector3d.YAxis), (-75.0, -Rhino.Geometry.Vector3d.YAxis)):
    sensor_ring = ring(Rhino.Geometry.Point3d(12.0, y, 116.0), direction, 2.2, 7.2, 3.6)
    sensor_lens = cylinder(Rhino.Geometry.Point3d(12.0, y + (2.3 if y > 0 else -2.3), 116.0), direction, 1.0, 3.2)
    add_brep(sensor_ring, "hardware", "SIDE_SENSOR_RING", COLORS["silver"])
    add_brep(sensor_lens, "sensors", "SIDE_SENSOR_LENS", COLORS["cyan"])


# 7. Rear service hatch and recessed handle.
rear_hatch = prism_yz(96.0, 99.0, 0.0, 112.0, 108.0, 82.0, 3.8)
rear_handle = prism_yz(99.2, 101.0, 0.0, 79.0, 44.0, 7.0, 4.2)
add_brep(rear_hatch, "rear", "REAR_SERVICE_HATCH", COLORS["white_alt"])
add_brep(rear_handle, "display", "REAR_HATCH_HANDLE", COLORS["black"])


# 8. Hidden footprint reference curves for quick dimension checking.
footprint_bottom = superellipse_xy(0.0, 200.0, 150.0, 2.0)
footprint_top = superellipse_xy(8.0, 200.0, 150.0, 2.0)
add_curve(footprint_bottom, "reference", "FOOTPRINT_200x150_BOTTOM", COLORS["gray"])
add_curve(footprint_top, "reference", "FOOTPRINT_200x150_TOP", COLORS["gray"])

DOC.Strings.SetString("M10_FOOTPRINT", "200 x 150 mm")
DOC.Strings.SetString("M10_BODY_HEIGHT", "183 mm including top sensor")
DOC.Strings.SetString("M10_SHELL_WALL_NOMINAL", "3.5 mm")
DOC.Strings.SetString("M10_SCREEN_MODULE", "75 x 45 x 4 mm reference envelope")
DOC.Strings.SetString("M10_SCREEN_OPENING", "76 x 46 mm; 0.5 mm clearance per side")
DOC.Strings.SetString("M10_MAINBOARD_REFERENCE", "90 x 60 x 2 mm with 24 x 8 mm cable slot")
DOC.Strings.SetString("M10_CHASSIS_INSERT", "192 x 142 mm ellipse; 0.5 mm clearance per side")
DOC.Strings.SetString("M10_REFERENCE", "User-supplied six-view M10 concept renders")

# Hide construction/reference layer after creating the verification curves.
reference_layer = DOC.Layers[LAYER_INDEX["reference"]]
reference_layer.IsVisible = False
DOC.Layers.Modify(reference_layer, reference_layer.Index, True)

DOC.Views.Redraw()

write_options = Rhino.FileIO.FileWriteOptions()
write_options.SuppressDialogBoxes = True
write_options.WriteSelectedObjectsOnly = False
if not DOC.WriteFile(OUTPUT_3DM, write_options):
    raise RuntimeError("Failed to save %s" % OUTPUT_3DM)

all_m10_objects = []
object_settings = Rhino.DocObjects.ObjectEnumeratorSettings()
object_settings.NormalObjects = True
object_settings.HiddenObjects = True
object_settings.LockedObjects = True
for obj in DOC.Objects.GetObjectList(object_settings):
    layer = DOC.Layers[obj.Attributes.LayerIndex]
    if layer and layer.FullPath.startswith("M10_"):
        all_m10_objects.append(obj)

bbox = Rhino.Geometry.BoundingBox.Empty
for obj in all_m10_objects:
    bbox.Union(obj.Geometry.GetBoundingBox(True))

print("M10 CAD build complete")
print("Removed prior M10 objects: %d" % deleted_count)
print("Created M10 objects: %d" % len(all_m10_objects))
print("Requested base footprint: 200.0 x 150.0 mm")
print(
    "Model bounding box: %.2f x %.2f x %.2f mm"
    % (bbox.Diagonal.X, bbox.Diagonal.Y, bbox.Diagonal.Z)
)
print("Saved: %s" % OUTPUT_3DM)
