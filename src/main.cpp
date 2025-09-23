#include <iostream>
#include <fstream>
#include <cmath>
#include <vector>

// physical constants
const double g = 9.81;
const double m1 = 1.0, m2 = 1.0, m3 = 1.0;
const double l1 = 1.0, l2 = 1.0, l3 = 1.0;

// state vector: [θ1, ω1, θ2, ω2, θ3, ω3]
struct State {
    double t1, w1;
    double t2, w2;
    double t3, w3;
};

struct Derivative {
    double dt1, dw1;
    double dt2, dw2;
    double dt3, dw3;
};

// equations of motion (simplified version for equal masses & lengths)
Derivative dynamics(const State &s) {
    Derivative d;

    // shorthand
    double t1 = s.t1, t2 = s.t2, t3 = s.t3;
    double w1 = s.w1, w2 = s.w2, w3 = s.w3;

    // very simplified equations (not exact full triple pendulum!)
    // for demonstration only — full equations are lengthy
    d.dt1 = w1;
    d.dt2 = w2;
    d.dt3 = w3;

    d.dw1 = -(g / l1) * sin(t1);
    d.dw2 = -(g / l2) * sin(t2);
    d.dw3 = -(g / l3) * sin(t3);

    return d;
}

// Runge-Kutta 4 integration
State rk4(const State &s, double dt) {
    Derivative k1 = dynamics(s);

    State s2 = { s.t1 + 0.5*dt*k1.dt1, s.w1 + 0.5*dt*k1.dw1,
                 s.t2 + 0.5*dt*k1.dt2, s.w2 + 0.5*dt*k1.dw2,
                 s.t3 + 0.5*dt*k1.dt3, s.w3 + 0.5*dt*k1.dw3 };
    Derivative k2 = dynamics(s2);

    State s3 = { s.t1 + 0.5*dt*k2.dt1, s.w1 + 0.5*dt*k2.dw1,
                 s.t2 + 0.5*dt*k2.dt2, s.w2 + 0.5*dt*k2.dw2,
                 s.t3 + 0.5*dt*k2.dt3, s.w3 + 0.5*dt*k2.dw3 };
    Derivative k3 = dynamics(s3);

    State s4 = { s.t1 + dt*k3.dt1, s.w1 + dt*k3.dw1,
                 s.t2 + dt*k3.dt2, s.w2 + dt*k3.dw2,
                 s.t3 + dt*k3.dt3, s.w3 + dt*k3.dw3 };
    Derivative k4 = dynamics(s4);

    State out;
    out.t1 = s.t1 + dt/6.0 * (k1.dt1 + 2*k2.dt1 + 2*k3.dt1 + k4.dt1);
    out.w1 = s.w1 + dt/6.0 * (k1.dw1 + 2*k2.dw1 + 2*k3.dw1 + k4.dw1);

    out.t2 = s.t2 + dt/6.0 * (k1.dt2 + 2*k2.dt2 + 2*k3.dt2 + k4.dt2);
    out.w2 = s.w2 + dt/6.0 * (k1.dw2 + 2*k2.dw2 + 2*k3.dw2 + k4.dw2);

    out.t3 = s.t3 + dt/6.0 * (k1.dt3 + 2*k2.dt3 + 2*k3.dt3 + k4.dt3);
    out.w3 = s.w3 + dt/6.0 * (k1.dw3 + 2*k2.dw3 + 2*k3.dw3 + k4.dw3);

    return out;
}

int main() {
    double dt = 0.01;
    int steps = 10000;

    // initial state
    State s { M_PI/2, 0.0, M_PI/2, 0.0, M_PI/2, 0.0 };

    std::ofstream file("triple_pendulum.csv");
    file << "x1,y1,x2,y2,x3,y3\n";

    for (int i = 0; i < steps; i++) {
        // compute cartesian positions
        double x1 = l1 * sin(s.t1);
        double y1 = -l1 * cos(s.t1);

        double x2 = x1 + l2 * sin(s.t2);
        double y2 = y1 - l2 * cos(s.t2);

        double x3 = x2 + l3 * sin(s.t3);
        double y3 = y2 - l3 * cos(s.t3);

        file << x1 << "," << y1 << ","
             << x2 << "," << y2 << ","
             << x3 << "," << y3 << "\n";

        s = rk4(s, dt);
    }

    file.close();
    std::cout << "Simulation complete. Data written to triple_pendulum.csv\n";
    return 0;
}

