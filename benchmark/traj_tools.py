import numpy as np
import numba
from numba import jit

NumericThresh = 1E-150
LogNumericThresh = np.log(NumericThresh)
EigenValueThresh = 1E-10

###########################################################################################################
##################################   General Utilities  ########################################
###########################################################################################################

@jit(nopython=True)
def sample_variance(zeroMeanDataArray,norm):
    """
    Compute the variance of a zero meaned array.  Divide by normalization factor.
    zero_mean_data_array    (required)  : float64 array of data
    norm                    (required)  : float64 value to divide variance by - supplied so one can substract appropriate values etc from normalization
    """
    # meta data from array
    nDataPoints = zeroMeanDataArray.shape[0]
    # zero variance
    var = np.float64(0.0)
    for i in range(nDataPoints):
        var += zeroMeanDataArray[i]**2
    return var/norm

# compute the covariance from trajectory data
# we assume the trajectory is aligned here
@jit(nopython=True)
def covar_3Nx3N_from_traj(traj_positions):
    # trajectory metadata
    n_frames = traj_positions.shape[0]
    n_atoms = traj_positions.shape[1]
    n_dim = traj_positions.shape[2]
    # Initialize average and covariance arrays
    avg = np.zeros((n_atoms*n_dim))
    covar = np.zeros((n_atoms*n_dim,n_atoms*n_dim))
    # loop over trajectory and compute average and covariance
    for ts in range(n_frames):
        flat = traj_positions[ts].flatten()
        avg += flat
        covar += np.outer(flat,flat)
    # finish averages
    avg /= n_frames
    covar /= n_frames-1
    # finish covar
    covar -= np.outer(avg,avg)
    return covar

@jit(nopython=True)
def covar_NxN_from_traj(traj_disp):
    # trajectory metadata
    n_frames = traj_disp.shape[0]
    n_atoms = traj_disp.shape[1]
    # declare covar
    covar = np.zeros((n_atoms,n_atoms),np.float64)
    # loop and compute
    for ts in range(n_frames):
        covar += np.dot(traj_disp[ts],traj_disp[ts].T)
    # symmetrize and average covar
    covar /= 3*(n_frames-1)
    # done, return
    return covar

@jit(nopython=True)
def pseudo_lpdet_inv(sigma):
    N = sigma.shape[0]
    e, v = np.linalg.eigh(sigma)
    precision = np.zeros(sigma.shape,dtype=np.float64)
    lpdet = 0.0
    rank = 0
    for i in range(N):
        if (e[i] > EigenValueThresh):
            lpdet += np.log(e[i])
            precision += 1.0/e[i]*np.outer(v[:,i],v[:,i])
            rank += 1
    return lpdet, precision, rank

@jit(nopython=True)
def lpdet_inv(sigma):
    N = sigma.shape[0]
    e, v = np.linalg.eigh(sigma)
    lpdet = 0.0
    for i in range(N):
        if (e[i] > EigenValueThresh):
            lpdet -= np.log(e[i])
    return lpdet

###########################################################################################################
##################################   Kabsch-related Routines       ########################################
###########################################################################################################


@jit(nopython=True)
def weight_kabsch_dist_align(x1, x2, weights):
    """
    Compute the Mahalabonis distance between positions x1 and x2 after aligned x1 to x2 given Kabsch weights (inverse variance)
    x1                      (required)  : float64 array with dimensions (n_atoms,3) of one molecular configuration
    x2                      (required)  : float64 array with dimensions (n_atoms,3) of another molecular configuration
    weights                 (required)  : float64 matrix with dimensions (n_atoms, n_atoms) of inverse (n_atoms, n_atoms) covariance
    """    
    x1_prime = weight_kabsch_rotate(x1, x2, weights)
    dist = 0.0
    for i in range(3):
        disp = x1_prime[:,i] - x2[:,i]
        dist += np.dot(disp,np.dot(weights,disp))
    return dist

@jit(nopython=True)
def weight_kabsch_dist(x1, x2, weights):
    """
    Compute the Mahalabonis distance between positions x1 and x2 given Kabsch weights (inverse variance)
    x1                      (required)  : float64 array with dimensions (n_atoms,3) of one molecular configuration
    x2                      (required)  : float64 array with dimensions (n_atoms,3) of another molecular configuration
    weights                 (required)  : float64 matrix with dimensions (n_atoms, n_atoms) of inverse (n_atoms, n_atoms) covariance
    """    
    dist = 0.0
    for i in range(3):
        disp = x1[:,i] - x2[:,i]
        dist += np.dot(disp,np.dot(weights,disp))
    return dist

@jit(nopython=True)
def weight_kabsch_rotate(mobile, target, weights):
    correlation_matrix = np.dot(np.transpose(mobile), np.dot(weights, target))
    V, S, W_tr = np.linalg.svd(correlation_matrix)
    if np.linalg.det(V) * np.linalg.det(W_tr) < 0.0:
        V[:, -1] = -V[:, -1]
    rotation = np.dot(V, W_tr)
    mobile_prime = np.dot(mobile,rotation)
    return mobile_prime

@jit(nopython=True)
def weight_kabsch_rmsd(mobile, target, weights):
    xyz1_prime = weight_kabsch_rotate(mobile, target, weights)
    delta = xyz1_prime - target
    rmsd = (delta ** 2.0).sum(1).mean() ** 0.5
    return rmsd

@jit(nopython=True)
def rmsd_kabsch(xyz1, xyz2):
    xyz1_prime = kabsch_rotate(xyz1, xyz2)
    delta = xyz1_prime - xyz2
    rmsd = (delta ** 2.0).sum(1).mean() ** 0.5
    return rmsd

@jit(nopython=True)
def kabsch_rotate(mobile, target):
    correlation_matrix = np.dot(np.transpose(mobile), target)
    V, S, W_tr = np.linalg.svd(correlation_matrix)
    if np.linalg.det(V) * np.linalg.det(W_tr) < 0.0:
        V[:, -1] = -V[:, -1]
    rotation = np.dot(V, W_tr)
    mobile_prime = np.dot(mobile,rotation) 
    return mobile_prime

@jit(nopython=True)
def kabsch_transform(mobile, target):
    translation, rotation = compute_translation_and_rotation(mobile, target)
    #mobile_prime = mobile.dot(rotation) + translation
    mobile_prime = np.dot(mobile,rotation) #+ translation
    return mobile_prime

@jit(nopython=True)
def compute_translation_and_rotation(mobile, target):
    #meta data
    n_atoms = mobile.shape[0]
    n_dim = mobile.shape[1]
    mu1 = np.zeros(n_dim)
    mu2 = np.zeros(n_dim)
    for i in range(n_atoms):
        for j in range(n_dim):
            mu1[j] += mobile[i,j]
            mu2[j] += target[i,j]
    mu1 /= n_atoms
    mu2 /= n_atoms
    mobile = mobile - mu1
    target = target - mu2

    correlation_matrix = np.dot(np.transpose(mobile), target)
    V, S, W_tr = np.linalg.svd(correlation_matrix)
    #is_reflection = (np.linalg.det(V) * np.linalg.det(W_tr)) < 0.0
    if np.linalg.det(V) * np.linalg.det(W_tr) < 0.0:
        V[:, -1] = -V[:, -1]
    rotation = np.dot(V, W_tr)

    translation = mu2 - np.dot(mu1,rotation)

    return translation, rotation

###########################################################################################################
##################################   Uniform Covariance Model      ########################################
###########################################################################################################

@jit(nopython=True)
def uniform_kabsch_log_lik(x, mu):
    # meta data
    n_frames = x.shape[0]
    n_atoms = x.shape[1]
    # compute log Likelihood for all points
    log_lik = 0.0
    sampleVar = 0.0
    for i in range(n_frames):
        for j in range(3):
            disp = x[i,:,j] - mu[:,j]
            temp = np.dot(disp,disp)
            sampleVar += temp
            log_lik += temp
    # finish variance
    sampleVar /= (n_frames-1)*3*(n_atoms-1)
    log_lik /= sampleVar
    log_lik +=  n_frames * 3 * (n_atoms-1) * np.log(sampleVar)
    log_lik *= -0.5
    return log_lik, sampleVar

@jit(nopython=True)
def align_maximum_likelihood_uniform(traj_positions,thresh=1E-10, max_steps=300, silent=False):
    """
    Perform maximum likelihood alignment of a trajecotry of particle positions.  The alignment is done with the uniform covariance model.  This model assumes that particles vary in equivalent, independent, spherical distributions.
    Inputs:
       traj_positions          (required)  : float64 array with dimensions (n_frames, n_atoms, 3) of particle positions
       thresh             (default: 1e-3)  : float64 scalar determining the log likelihood difference deemed to be converged
       max_steps           (default: 300)  : int scalar capping the number of iterations attempted if convergence criteria is not met
    Outputs:
       aligned_positions                   : float64 array with dimensions (n_frames, n_atoms, 3) of aligned particle positions
       avg                                 : float64 array with dimensions (n_atoms, 3) of the average structure after alignment
       particle_variance                   : float64 scalar of average particle variance after alignment
    """
    # trajectory metadata
    n_frames = traj_positions.shape[0]
    n_atoms = traj_positions.shape[1]
    n_dim = traj_positions.shape[2]
    # create numpy array of aligned positions
    aligned_pos = np.copy(traj_positions).astype(np.float64)
    # start be removing COG translation
    for ts in range(n_frames):
        mu = np.zeros(n_dim)
        for atom in range(n_atoms):
            mu += aligned_pos[ts,atom]
        mu /= n_atoms
        aligned_pos[ts] -= mu
    # Initialize average as first frame
    avg = np.copy(aligned_pos[0]).astype(np.float64)
    log_lik, var = uniform_kabsch_log_lik(aligned_pos,avg)
    # perform iterative alignment and average to converge log likelihood
    log_lik_diff = 10
    step = 1
    if silent == False:
        print("Iteration   Log Likelihood     Delta Log Likelihood")
        print("-----------------------------------------------------------------")
    while log_lik_diff > thresh and step < max_steps:
        # rezero new average
        new_avg = np.zeros((n_atoms,n_dim),dtype=np.float64)
        # align trajectory to average and accumulate new average
        for ts in range(n_frames):
            aligned_pos[ts] = kabsch_rotate(aligned_pos[ts], avg)
            new_avg += aligned_pos[ts]
        # finish average
        new_avg /= n_frames
        # compute log likelihood
        new_log_lik, var = uniform_kabsch_log_lik(aligned_pos,avg)
        log_lik_diff = np.abs(new_log_lik-log_lik)
        log_lik = new_log_lik
        # copy new average
        avg = np.copy(new_avg)
        step += 1
        if silent == False:
            print(step, log_lik, log_lik_diff)
            #print("%10d %20.8f %20.8f" % (step, log_lik, log_lik_diff))
            #print('{10d} {20.8f} {20.8f}'.format(step, log_lik, log_lik_diff))
            #print('{10d}'.format(step), '{20.8f}'.format(log_lik), '{20.8f}'.format(log_lik_diff))
    return aligned_pos, avg, var

###########################################################################################################
##################################   Intermediate Covariance Model ########################################
###########################################################################################################

@jit(nopython=True)
def intermediate_kabsch_log_lik(x, mu, kabsch_weights):
    # meta data
    n_frames = x.shape[0]
    lpdet = lpdet_inv(kabsch_weights) 
    # compute log Likelihood for all points
    log_lik = 0.0
    for i in range(n_frames):
        #disp = x[i] - mu
        for j in range(3):
            disp = x[i,:,j] - mu[:,j]
            log_lik += np.dot(disp,np.dot(kabsch_weights,disp))
    log_lik += 3 * n_frames * lpdet
    log_lik *= -0.5
    return log_lik


# compute variance of each particle from a trajectory and average structure
@jit(nopython=True)
def particle_variances_from_trajectory(traj_positions, avg):
    # meta data
    n_frames = traj_positions.shape[0]
    n_atoms = traj_positions.shape[1]
    # 
    disp = traj_positions - avg
    particle_variances = np.zeros(n_atoms,dtype=np.float64)
    for ts in range(n_frames):
        for atom in range(n_atoms):
            particle_variances[atom] += np.dot(disp[ts,atom],disp[ts,atom])
    particle_variances /= 3*(n_frames-1)
    return particle_variances


# Compute the intermediate kabsch weights from variances
@jit(nopython=True)
def intermediate_kabsch_weights(variances):
    # meta data
    n_atoms = variances.shape[0]
    # kasbch weights are inverse of variances
    inverseVariances = np.power(variances,-1)
    kabsch_weights = np.zeros((n_atoms,n_atoms),dtype=np.float64)
    # force constant vector to be null space of kabsch weights
    wsum = np.sum(inverseVariances)
    for i in range(n_atoms):
        # Populate diagonal elements
        kabsch_weights[i,i] = inverseVariances[i]
        for j in range(n_atoms):
            kabsch_weights[i,j] -= inverseVariances[i]*inverseVariances[j]/wsum
    # return the weights
    return kabsch_weights

# compute the average structure and covariance from trajectory data
@jit(nopython=True)
def align_maximum_likelihood_intermediate(traj_positions,thresh=1E-3,max_steps=300):
    """
    Perform maximum likelihood alignment of a trajecotry of particle positions.  The alignment is done with the intermediate covariance model.  This model assumes that particles vary in different, independent, spherical distributions.
    Inputs:
       traj_positions          (required)  : float64 array with dimensions (n_frames, n_atoms, 3) of particle positions
       thresh             (default: 1e-3)  : float64 scalar determining the log likelihood difference deemed to be converged
       max_steps           (default: 300)  : int scalar capping the number of iterations attempted if convergence criteria is not met
    Outputs:
       aligned_positions                   : float64 array with dimensions (n_frames, n_atoms, 3) of aligned particle positions
       avg                                 : float64 array with dimensions (n_atoms, 3) of the average structure after alignment
       particle_variances                  : float64 array with dimensions (n_atoms) of the variance of each particle after alignment
    """
    # trajectory metadata
    n_frames = traj_positions.shape[0]
    n_atoms = traj_positions.shape[1]
    n_dim = traj_positions.shape[2]
    # Initialize with uniform alignment
    aligned_pos, avg = align_maximum_likelihood_uniform(traj_positions,thresh,max_steps,silent=True)[:2]
    # Compute Kabsch Weights
    particle_variances = particle_variances_from_trajectory(aligned_pos, avg)
    kabsch_weights = intermediate_kabsch_weights(particle_variances)
    log_lik = intermediate_kabsch_log_lik(aligned_pos,avg,kabsch_weights)
    # perform iterative alignment and average to converge average
    log_lik_diff = 10
    step = 0
    print("Iteration   Log Likelihood     Delta Log Likelihood")
    print("-----------------------------------------------------------------")
    while log_lik_diff > thresh and step < max_steps:
        # rezero new average
        new_avg = np.zeros((n_atoms,n_dim),dtype=np.float64)
        # align trajectory to average and accumulate new average
        weighted_avg = np.dot(kabsch_weights, avg)
        for ts in range(n_frames):
            aligned_pos[ts] = kabsch_rotate(aligned_pos[ts], weighted_avg)
            new_avg += aligned_pos[ts]
        # finish average
        new_avg /= n_frames
        # compute log likelihood
        new_log_lik = intermediate_kabsch_log_lik(aligned_pos,avg,kabsch_weights)
        log_lik_diff = np.abs(new_log_lik-log_lik)
        log_lik = new_log_lik
        # compute new Kabsch Weights
        particle_variances = particle_variances_from_trajectory(aligned_pos,new_avg)
        kabsch_weights = intermediate_kabsch_weights(particle_variances)
        step += 1
        print(step, log_lik, log_lik_diff)
        #print("%10d %20.8f %20.8f" % (step, log_lik, log_lik_diff))
        #print('{10d}'.format(step), '{20.8f}'.format(log_lik), '{20.8f}'.format(log_lik_diff))
    return aligned_pos, avg, particle_variances


###########################################################################################################
##################################   Weighted Covariance Model ########################################
###########################################################################################################

@jit(nopython=True)
def weight_kabsch_log_lik(x, mu, precision, lpdet):
    # meta data
    n_frames = x.shape[0]
    # compute log Likelihood for all points
    log_lik = 0.0
    for i in range(n_frames):
        #disp = x[i] - mu
        for j in range(3):
            disp = x[i,:,j] - mu[:,j]
            log_lik += np.dot(disp,np.dot(precision,disp))
    log_lik += 3 * n_frames * lpdet
    log_lik *= -0.5
    return log_lik

# Perform weighted maximum likelihood trajectory alignment
@jit(nopython=True)
def align_maximum_likelihood_weighted(traj_positions,thresh=1E-3,max_steps=300):
    """
    Perform maximum likelihood alignment of a trajecotry of particle positions.  The alignment is done with the weighted covariance model.  This model assumes that particles vary in different, coupled, spherical distributions.
    Inputs:
       traj_positions          (required)  : float64 array with dimensions (n_frames, n_atoms, 3) of particle positions
       thresh             (default: 1e-3)  : float64 scalar determining the log likelihood difference deemed to be converged
       max_steps           (default: 300)  : int scalar capping the number of iterations attempted if convergence criteria is not met
    Outputs:
       aligned_positions                   : float64 array with dimensions (n_frames, n_atoms, 3) of aligned particle positions
       avg                                 : float64 array with dimensions (n_atoms, 3) of the average structure after alignment
       covariance                          : float64 array with dimensions (n_atoms, n_atoms) of the covariance particles after alignment
    """
    # trajectory metadata
    n_frames = traj_positions.shape[0]
    n_atoms = traj_positions.shape[1]
    n_dim = traj_positions.shape[2]
    # Initialize with uniform weighted Kabsch
    aligned_pos, avg = align_maximum_likelihood_uniform(traj_positions,thresh,max_steps,silent=True)[:2]
    # compute NxN covar
    covar = covar_NxN_from_traj(aligned_pos-avg)
    # determine precision and pseudo determinant 
    lpdet, precision, rank = pseudo_lpdet_inv(covar)
    # compute log likelihood
    log_lik = weight_kabsch_log_lik(aligned_pos, avg, precision, lpdet)
    # perform iterative alignment and average to converge average
    log_lik_diff = 10+thresh
    step = 0
    print("Iteration   Log Likelihood     Delta Log Likelihood")
    print("-----------------------------------------------------------------")
    while log_lik_diff > thresh and step < max_steps:
        # rezero new average
        new_avg = np.zeros((n_atoms,n_dim),dtype=np.float64)
        # align trajectory to average and accumulate new average
        weighted_avg = np.dot(precision,avg)
        for ts in range(n_frames):
            aligned_pos[ts] = kabsch_rotate(aligned_pos[ts], weighted_avg)
            new_avg += aligned_pos[ts]
        # finish average
        new_avg /= n_frames
        # compute new Kabsch Weights
        covar = covar_NxN_from_traj(aligned_pos-new_avg)
        # determine precision and pseudo determinant 
        lpdet, precision, rank = pseudo_lpdet_inv(covar)
        # compute log likelihood
        new_log_lik = weight_kabsch_log_lik(aligned_pos, new_avg, precision, lpdet)
        log_lik_diff = np.abs(new_log_lik-log_lik)
        log_lik = new_log_lik
        avg = np.copy(new_avg)
        step += 1
        print(step, log_lik, log_lik_diff)
        #print("%10d %20.8f %20.8f" % (step, log_lik, log_lik_diff))
        #print('{10d} {20.8f} {20.8f}'.format(step, log_lik, log_lik_diff))
        #print('{10d}'.format(step), '{20.8f}'.format(log_lik), '{20.8f}'.format(log_lik_diff))
    return aligned_pos, avg, np.linalg.pinv(precision, rcond=1e-10)

######################################  Non-iterative alignment protocols ##############################################


# align trajectory data to a reference structure
@jit(nopython=True)
def align_traj_to_ref_weighted_kabsch(traj_positions,ref, covar):
    # trajectory metadata
    n_frames = traj_positions.shape[0]
    # kabsch weights
    kabsch_weights = np.linalg.pinv(covar,rcond=1e-10)
    # create numpy array of aligned positions
    aligned_positions = np.copy(traj_positions)
    for ts in range(n_frames):
        # align positions based on weighted Kabsch
        aligned_positions[ts] = weight_kabsch_rotate(aligned_positions[ts], ref, kabsch_weights)
    return aligned_positions

# align trajectory data to a reference structure
@jit(nopython=True)
def align_traj_to_ref_uniform_kabsch(traj_positions,ref):
    # trajectory metadata
    n_frames = traj_positions.shape[0]
    # create numpy array of aligned positions
    aligned_positions = np.copy(traj_positions)
    for ts in range(n_frames):
        # make sure positions are centered
        aligned_positions[ts] = kabsch_rotate(aligned_positions[ts], ref)
    return aligned_positions

