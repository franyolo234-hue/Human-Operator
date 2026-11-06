// ============================================================
// VoiceHaptic — Forearm Controller Housing
// ============================================================
// 3D-printable enclosure for ESP32-S3, TCA9548A, DRV2605L stack,
// battery, and charging circuitry. Mounts on the forearm via
// Velcro straps. Designed for PLA or PETG printing.
//
// Author: VoiceHaptic Project (Johannesheim / Aurora Prize)
// License: MIT
// Units: millimeters
// ============================================================

// === PARAMETERS (adjust to fit your components) ===

// ESP32-S3 DevKitC-1 dimensions
esp32_l = 69;   // length
esp32_w = 26;   // width
esp32_h = 12;   // height including pins

// Perf board stack (DRV2605L × 8 + TCA9548A)
board_l = 70;   // 5×7cm perf board
board_w = 50;
board_h = 18;   // stacked with breakouts

// Battery (503035 LiPo)
bat_l = 35;
bat_w = 30;
bat_h = 5;

// TP4056 charger module
chrg_l = 26;
chrg_w = 17;
chrg_h = 4;

// Enclosure parameters
wall = 2.0;         // wall thickness
corner_r = 3.0;     // corner radius
lid_lip = 1.5;      // lid overlap
gap = 0.5;          // clearance around components

// Strap slots
strap_w = 22;       // Velcro strap width
strap_h = 3;        // slot height
strap_offset = 10;  // from edges

// Internal layout
padding = 2.0;

// Computed dimensions
inner_l = board_l + gap * 2;
inner_w = max(board_w, esp32_l) + gap * 2;
inner_h = board_h + bat_h + padding * 2;

outer_l = inner_l + wall * 2;
outer_w = inner_w + wall * 2;
outer_h = inner_h + wall * 2;

// USB-C port cutout
usb_w = 10;
usb_h = 4;

// Microphone hole
mic_d = 4;

// === MODULES ===

module rounded_box(l, w, h, r) {
    hull() {
        for (x = [r, l - r])
            for (y = [r, w - r])
                translate([x, y, 0])
                    cylinder(h = h, r = r, $fn = 32);
    }
}

module strap_slot(l, w, h) {
    // Rounded slot for Velcro strap
    hull() {
        translate([0, 0, 0]) cylinder(d = h, h = w, $fn = 16);
        translate([l, 0, 0]) cylinder(d = h, h = w, $fn = 16);
    }
}

// === MAIN BODY (bottom half) ===

module housing_body() {
    difference() {
        // Outer shell
        rounded_box(outer_l, outer_w, outer_h / 2 + lid_lip, corner_r);

        // Inner cavity
        translate([wall, wall, wall])
            rounded_box(inner_l, inner_w, outer_h, corner_r - wall / 2);

        // USB-C port (ESP32 side)
        translate([wall + inner_l / 2 - usb_w / 2, -1, wall + 3])
            cube([usb_w, wall + 2, usb_h]);

        // Charging USB-C port (TP4056 side)
        translate([wall + inner_l - 15, outer_w - wall - 1, wall + 2])
            cube([usb_w, wall + 2, usb_h]);

        // Microphone hole (top face — will be in lid)
        // (kept here for alignment reference)

        // Strap slots — left side
        translate([-1, outer_w / 2, outer_h / 4])
            rotate([90, 0, 90])
                strap_slot(strap_w, wall + 2, strap_h);

        // Strap slots — right side
        translate([outer_l - wall - 1, outer_w / 2, outer_h / 4])
            rotate([90, 0, 90])
                strap_slot(strap_w, wall + 2, strap_h);

        // Ventilation holes (bottom)
        for (i = [0:4])
            translate([wall + 10 + i * 12, wall + 5, -1])
                cylinder(d = 2, h = wall + 2, $fn = 16);

        // Cable exit hole (for actuator ribbon cable)
        translate([outer_l / 2, outer_w - wall - 1, wall + inner_h / 2])
            rotate([-90, 0, 0])
                cylinder(d = 8, h = wall + 2, $fn = 24);

        // Screw post holes
        for (pos = [
            [wall + 3, wall + 3, wall],
            [outer_l - wall - 3, wall + 3, wall],
            [wall + 3, outer_w - wall - 3, wall],
            [outer_l - wall - 3, outer_w - wall - 3, wall]
        ])
            translate(pos)
                cylinder(d = 2.2, h = outer_h, $fn = 16);
    }

    // Screw posts (inside)
    for (pos = [
        [wall + 3, wall + 3, wall],
        [outer_l - wall - 3, wall + 3, wall],
        [wall + 3, outer_w - wall - 3, wall],
        [outer_l - wall - 3, outer_w - wall - 3, wall]
    ])
        translate(pos)
            difference() {
                cylinder(d = 5, h = inner_h / 2, $fn = 24);
                cylinder(d = 1.8, h = inner_h / 2 + 1, $fn = 16);
            }

    // Component mounting rails
    // ESP32 rail
    translate([wall + gap, wall + gap, wall])
        cube([2, esp32_l + gap, 2]);
    translate([wall + gap + esp32_w + gap, wall + gap, wall])
        cube([2, esp32_l + gap, 2]);
}

// === LID ===

module housing_lid() {
    difference() {
        union() {
            // Lid plate
            rounded_box(outer_l, outer_w, wall, corner_r);

            // Inner lip for alignment
            translate([wall + 0.3, wall + 0.3, wall])
                rounded_box(inner_l - 0.6, inner_w - 0.6, lid_lip, corner_r - wall / 2);
        }

        // Microphone hole
        translate([outer_l / 2 - 15, outer_w / 2, -1])
            cylinder(d = mic_d, h = wall + lid_lip + 2, $fn = 24);

        // Acoustic mesh area (tiny holes around mic)
        for (a = [0:45:359])
            translate([outer_l / 2 - 15 + cos(a) * 5, outer_w / 2 + sin(a) * 5, -1])
                cylinder(d = 1.2, h = wall + lid_lip + 2, $fn = 12);

        // Status LED light pipes
        translate([outer_l - wall - 10, outer_w / 2 - 5, -1])
            cylinder(d = 3.2, h = wall + lid_lip + 2, $fn = 16);
        translate([outer_l - wall - 10, outer_w / 2 + 5, -1])
            cylinder(d = 3.2, h = wall + lid_lip + 2, $fn = 16);

        // Emergency stop button hole
        translate([wall + 10, outer_w / 2, -1])
            cylinder(d = 7, h = wall + lid_lip + 2, $fn = 24);

        // Screw holes
        for (pos = [
            [wall + 3, wall + 3, -1],
            [outer_l - wall - 3, wall + 3, -1],
            [wall + 3, outer_w - wall - 3, -1],
            [outer_l - wall - 3, outer_w - wall - 3, -1]
        ])
            translate(pos)
                cylinder(d = 2.2, h = wall + lid_lip + 2, $fn = 16);
    }
}

// === ACTUATOR POD (finger mount) ===

module actuator_pod(lra_d = 10, lra_h = 3.4) {
    // Flexible pod that holds one LRA coin actuator
    // Print in TPU for comfort and flexibility
    pod_wall = 1.2;
    pod_d = lra_d + pod_wall * 2 + 1;
    pod_h = lra_h + pod_wall + 1;
    tab_l = 12;
    tab_w = pod_d;
    tab_h = 1.5;

    difference() {
        union() {
            // Main cylindrical pod
            cylinder(d = pod_d, h = pod_h, $fn = 32);

            // Sewing/glue tab (attaches to glove)
            translate([-tab_l / 2, -tab_w / 2, 0])
                cube([tab_l, tab_w, tab_h]);

            // Second tab (opposite side)
            translate([pod_d / 2, -tab_w / 2, 0])
                cube([tab_l / 2, tab_w, tab_h]);
        }

        // LRA cavity
        translate([0, 0, pod_wall])
            cylinder(d = lra_d + 0.5, h = lra_h + 1, $fn = 32);

        // Wire channel
        translate([0, 0, pod_wall])
            rotate([0, 90, 0])
                cylinder(d = 3, h = pod_d, $fn = 16);

        // Sewing holes in tabs
        for (x = [-tab_l / 2 + 2, -tab_l / 2 + 8])
            for (y = [-3, 3])
                translate([x, y, -1])
                    cylinder(d = 1.5, h = tab_h + 2, $fn = 12);

        for (x = [pod_d / 2 + 2])
            for (y = [-3, 3])
                translate([x, y, -1])
                    cylinder(d = 1.5, h = tab_h + 2, $fn = 12);
    }
}

// === WRIST BAND ACTUATOR HOLDER ===

module wrist_band_holder() {
    // Holds 2 LRAs (volar + dorsal) with strap attachment
    // Print in TPU
    band_l = 40;
    band_w = 25;
    band_h = 6;
    lra_d = 10;

    difference() {
        // Base band section
        hull() {
            translate([0, 0, 0])
                cylinder(d = band_w, h = band_h, $fn = 32);
            translate([band_l, 0, 0])
                cylinder(d = band_w, h = band_h, $fn = 32);
        }

        // LRA cavity 1 (volar)
        translate([8, 0, 1.2])
            cylinder(d = lra_d + 0.5, h = 4, $fn = 32);

        // LRA cavity 2 (dorsal)
        translate([band_l - 8, 0, 1.2])
            cylinder(d = lra_d + 0.5, h = 4, $fn = 32);

        // Wire channels
        translate([8, 0, 3])
            rotate([0, 90, 0])
                cylinder(d = 3, h = band_l - 16, $fn = 16);

        // Strap slots
        translate([-band_w / 2 + 2, -strap_w / 2, -1])
            cube([3, strap_w, band_h + 2]);
        translate([band_l + band_w / 2 - 5, -strap_w / 2, -1])
            cube([3, strap_w, band_h + 2]);
    }
}

// === RENDER ===

// Uncomment the part you want to print:

// Main housing body
housing_body();

// Lid (translate for visibility)
translate([0, outer_w + 10, 0])
    housing_lid();

// Actuator pod (print 7× for fingers + forearm)
translate([0, -30, 0])
    actuator_pod();

// Wrist band holder
translate([0, -60, 0])
    wrist_band_holder();
