import numpy as np
from numba import njit


@njit(cache=True)
def mac_vels(qx, qy, ng, dx, dy, dt,
             u, v,
             ldelta_ux, ldelta_vx,
             ldelta_uy, ldelta_vy,
             gradp_x, gradp_y):

    u_MAC = np.zeros((qx, qy))
    v_MAC = np.zeros((qx, qy))

    # get the full u and v left and right states (including transverse
    # terms) on both the x- and y-interfaces
    u_xl, u_xr, u_yl, u_yr, v_xl, v_xr, v_yl, v_yr = get_interface_states(qx, qy, ng, dx, dy, dt,
                                                                          u, v,
                                                                          ldelta_ux, ldelta_vx,
                                                                          ldelta_uy, ldelta_vy,
                                                                          gradp_x, gradp_y)

    # Riemann problem -- this follows Burger's equation.  We don't use
    # any input velocity for the upwinding.  Also, we only care about
    # the normal states here (u on x and v on y)
    riemann_and_upwind(qx, qy, ng, u_xl, u_xr, u_MAC)
    riemann_and_upwind(qx, qy, ng, v_yl, v_yr, v_MAC)

    return u_MAC, v_MAC


# xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
@njit(cache=True)
def states(qx, qy, ng, dx, dy, dt,
           u, v,
           ldelta_ux, ldelta_vx,
           ldelta_uy, ldelta_vy,
           gradp_x, gradp_y,
           u_MAC, v_MAC):
    """
    this is similar to mac_vels, but it predicts the interface states
    of both u and v on both interfaces, using the MAC velocities to
    do the upwinding.
    """

    u_xint = np.zeros((qx, qy))
    u_yint = np.zeros((qx, qy))
    v_xint = np.zeros((qx, qy))
    v_yint = np.zeros((qx, qy))

    # get the full u and v left and right states (including transverse
    # terms) on both the x- and y-interfaces
    u_xl, u_xr, u_yl, u_yr, v_xl, v_xr, v_yl, v_yr = get_interface_states(qx, qy, ng, dx, dy, dt,
                                                                          u, v,
                                                                          ldelta_ux, ldelta_vx,
                                                                          ldelta_uy, ldelta_vy,
                                                                          gradp_x, gradp_y)

    # upwind using the MAC velocity to determine which state exists on
    # the interface
    upwind(qx, qy, ng, u_xl, u_xr, u_MAC, u_xint)
    upwind(qx, qy, ng, v_xl, v_xr, u_MAC, v_xint)
    upwind(qx, qy, ng, u_yl, u_yr, v_MAC, u_yint)
    upwind(qx, qy, ng, v_yl, v_yr, v_MAC, v_yint)

    return u_xint, u_yint, v_xint, v_yint


# xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
@njit(cache=True)
def get_interface_states(qx, qy, ng, dx, dy, dt,
                         u, v,
                         ldelta_ux, ldelta_vx,
                         ldelta_uy, ldelta_vy,
                         gradp_x, gradp_y):
    """
    Compute the unsplit predictions of u and v on both the x- and
    y-interfaces.  This includes the transverse terms.
    """

    u_xl = np.zeros((qx, qy))
    u_xr = np.zeros((qx, qy))
    u_yl = np.zeros((qx, qy))
    u_yr = np.zeros((qx, qy))

    v_xl = np.zeros((qx, qy))
    v_xr = np.zeros((qx, qy))
    v_yl = np.zeros((qx, qy))
    v_yr = np.zeros((qx, qy))

    uhat_adv = np.zeros((qx, qy))
    vhat_adv = np.zeros((qx, qy))

    u_xint = np.zeros((qx, qy))
    u_yint = np.zeros((qx, qy))
    v_xint = np.zeros((qx, qy))
    v_yint = np.zeros((qx, qy))

    nx = qx - 2 * ng
    ny = qy - 2 * ng
    ilo = ng
    ihi = ng + nx
    jlo = ng
    jhi = ng + ny

    # first predict u and v to both interfaces, considering only the normal
    # part of the predictor.  These are the 'hat' states.

    dtdx = dt / dx
    dtdy = dt / dy

    for j in range(jlo - 2, jhi + 3):
        for i in range(ilo - 2, ihi + 3):

            # u on x-edges
            u_xl[i + 1, j] = u[i, j] + 0.5 * \
                (1.0 - dtdx * u[i, j]) * ldelta_ux[i, j]
            u_xr[i, j] = u[i, j] - 0.5 * \
                (1.0 + dtdx * u[i, j]) * ldelta_ux[i, j]

            # v on x-edges
            v_xl[i + 1, j] = v[i, j] + 0.5 * \
                (1.0 - dtdx * u[i, j]) * ldelta_vx[i, j]
            v_xr[i, j] = v[i, j] - 0.5 * \
                (1.0 + dtdx * u[i, j]) * ldelta_vx[i, j]

            # u on y-edges
            u_yl[i, j + 1] = u[i, j] + 0.5 * \
                (1.0 - dtdy * v[i, j]) * ldelta_uy[i, j]
            u_yr[i, j] = u[i, j] - 0.5 * \
                (1.0 + dtdy * v[i, j]) * ldelta_uy[i, j]

            # v on y-edges
            v_yl[i, j + 1] = v[i, j] + 0.5 * \
                (1.0 - dtdy * v[i, j]) * ldelta_vy[i, j]
            v_yr[i, j] = v[i, j] - 0.5 * \
                (1.0 + dtdy * v[i, j]) * ldelta_vy[i, j]

    # now get the normal advective velocities on the interfaces by solving
    # the Riemann problem.
    riemann(qx, qy, ng, u_xl, u_xr, uhat_adv)
    riemann(qx, qy, ng, v_yl, v_yr, vhat_adv)

    # now that we have the advective velocities, upwind the left and right
    # states using the appropriate advective velocity.

    # on the x-interfaces, we upwind based on uhat_adv
    upwind(qx, qy, ng, u_xl, u_xr, uhat_adv, u_xint)
    upwind(qx, qy, ng, v_xl, v_xr, uhat_adv, v_xint)

    # on the y-interfaces, we upwind based on vhat_adv
    upwind(qx, qy, ng, u_yl, u_yr, vhat_adv, u_yint)
    upwind(qx, qy, ng, v_yl, v_yr, vhat_adv, v_yint)

    # at this point, these states are the `hat' states -- they only
    # considered the normal to the interface portion of the predictor.

    # add the transverse flux differences to the preliminary interface states
    for j in range(jlo - 2, jhi + 3):
        for i in range(ilo - 2, ihi + 3):

            ubar = 0.5 * (uhat_adv[i, j] + uhat_adv[i + 1, j])
            vbar = 0.5 * (vhat_adv[i, j] + vhat_adv[i, j + 1])

            # v du/dy is the transerse term for the u states on x-interfaces
            vu_y = vbar * (u_yint[i, j + 1] - u_yint[i, j])

            u_xl[i + 1, j] = u_xl[i + 1, j] - 0.5 * \
                dtdy * vu_y - 0.5 * dt * gradp_x[i, j]
            u_xr[i, j] = u_xr[i, j] - 0.5 * dtdy * \
                vu_y - 0.5 * dt * gradp_x[i, j]

            # v dv/dy is the transverse term for the v states on x-interfaces
            vv_y = vbar * (v_yint[i, j + 1] - v_yint[i, j])

            v_xl[i + 1, j] = v_xl[i + 1, j] - 0.5 * \
                dtdy * vv_y - 0.5 * dt * gradp_y[i, j]
            v_xr[i, j] = v_xr[i, j] - 0.5 * dtdy * \
                vv_y - 0.5 * dt * gradp_y[i, j]

            # u dv/dx is the transverse term for the v states on y-interfaces
            uv_x = ubar * (v_xint[i + 1, j] - v_xint[i, j])

            v_yl[i, j + 1] = v_yl[i, j + 1] - 0.5 * \
                dtdx * uv_x - 0.5 * dt * gradp_y[i, j]
            v_yr[i, j] = v_yr[i, j] - 0.5 * dtdx * \
                uv_x - 0.5 * dt * gradp_y[i, j]

            # u du/dx is the transverse term for the u states on y-interfaces
            uu_x = ubar * (u_xint[i + 1, j] - u_xint[i, j])

            u_yl[i, j + 1] = u_yl[i, j + 1] - 0.5 * \
                dtdx * uu_x - 0.5 * dt * gradp_x[i, j]
            u_yr[i, j] = u_yr[i, j] - 0.5 * dtdx * \
                uu_x - 0.5 * dt * gradp_x[i, j]

    return u_xl, u_xr, u_yl, u_yr, v_xl, v_xr, v_yl, v_yr


# xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
@njit(cache=True)
def upwind(qx, qy, ng, q_l, q_r, s, q_int):
    """
    upwind the left and right states based on the specified input
    velocity, s.  The resulting interface state is q_int
    """

    nx = qx - 2 * ng
    ny = qy - 2 * ng
    ilo = ng
    ihi = ng + nx
    jlo = ng
    jhi = ng + ny

    for j in range(jlo - 1, jhi + 2):
        for i in range(ilo - 1, ihi + 2):

            if (s[i, j] > 0.0):
                q_int[i, j] = q_l[i, j]
            elif (s[i, j] == 0.0):
                q_int[i, j] = 0.5 * (q_l[i, j] + q_r[i, j])
            else:
                q_int[i, j] = q_r[i, j]


# xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
@njit(cache=True)
def riemann(qx, qy, ng, q_l, q_r, s):
    """
    Solve the Burger's Riemann problem given the input left and right
    states and return the state on the interface.

    This uses the expressions from Almgren, Bell, and Szymczak 1996.
    """

    nx = qx - 2 * ng
    ny = qy - 2 * ng
    ilo = ng
    ihi = ng + nx
    jlo = ng
    jhi = ng + ny

    for j in range(jlo - 1, jhi + 2):
        for i in range(ilo - 1, ihi + 2):

            if (q_l[i, j] > 0.0 and q_l[i, j] + q_r[i, j] > 0.0):
                s[i, j] = q_l[i, j]
            elif (q_l[i, j] <= 0.0 and q_r[i, j] >= 0.0):
                s[i, j] = 0.0
            else:
                s[i, j] = q_r[i, j]


# xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
@njit(cache=True)
def riemann_and_upwind(qx, qy, ng, q_l, q_r, q_int):
    """
    First solve the Riemann problem given q_l and q_r to give the
    velocity on the interface and: use this velocity to upwind to
    determine the state (q_l, q_r, or a mix) on the interface).

    This differs from upwind, above, in that we don't take in a
    velocity to upwind with).
    """

    s = np.zeros((qx, qy))

    riemann(qx, qy, ng, q_l, q_r, s)
    upwind(qx, qy, ng, q_l, q_r, s, q_int)
