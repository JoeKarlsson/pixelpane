// Light grid ("egg crate") for a HUB75 LED panel.
//
// It sits flat on the panel so every LED lights its own crisp square instead of
// a soft blob, and holds the diffuser / two-way mirror at a fixed distance.
// Measure your panel before printing: pitch is printed on the back (P4, P5, P6 =
// 4, 5, 6 mm between LED centers), and a 32x32 panel is 32 * pitch wide.
//
// Big panels outgrow most print beds: set tiles = 2 to cut the grid into 2x2
// pieces and print each one with tile_x / tile_y (0 or 1).

rows   = 32;     // LEDs down
cols   = 32;     // LEDs across
pitch  = 6;      // mm between LED centers (P6 = 6)
wall   = 0.8;    // wall thickness: two lines with a 0.4 mm nozzle
height = 10;     // depth in mm: deeper = sharper squares (8-15 works well)
rim    = 0;      // solid border in mm; 0 = grid exactly the panel's size

tiles  = 1;      // 1 = one piece; 2 = 2x2 pieces; 4 = 4x4 pieces
tile_x = 0;      // which piece to print, 0 .. tiles-1
tile_y = 0;

w = cols * pitch + 2 * rim;
h = rows * pitch + 2 * rim;

module grid() {
    difference() {
        cube([w, h, height]);
        for (x = [0 : cols - 1], y = [0 : rows - 1])
            translate([rim + x * pitch + wall / 2, rim + y * pitch + wall / 2, -1])
                cube([pitch - wall, pitch - wall, height + 2]);
    }
}

intersection() {
    grid();
    translate([tile_x * w / tiles, tile_y * h / tiles, -1])
        cube([w / tiles, h / tiles, height + 2]);
}
