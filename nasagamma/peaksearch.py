
"""
Created on Wed Sep 30 15:08:07 2020

@author: mauricio
"""
import numpy as np
from . import spectrum as sp
from scipy.signal import find_peaks
import matplotlib.pyplot as plt

 
def gaussian(x, mean, sigma):
    '''
    Gaussian function.

    Parameters
    ----------
    x : numpy array.
        x-values.
    mean : float or int.
        mean of distribution.
    sigma : float or int.
        standard deviation.

    Returns
    -------
    numpy array.
        Gaussian distribution.
    '''
    z = (x - mean) / sigma
    return np.exp(-z**2 / 2.)

def gaussian_derivative(x, mean, sigma):
    '''
    First derivative of a Gaussian.

    Parameters
    ----------
    x : numpy array.
        x-values.
    mean : float or int.
        mean of distribution.
    sigma : float or int.
        standard deviation.

    Returns
    -------
    numpy array
        first derivaive of a Gaussian.

    '''
    z = (x - mean)
    return -1 * z * gaussian(x, mean, sigma)


class PeakSearch:
    
    def __init__(self, spectrum, ref_x, ref_fwhm, fwhm_at_0=1.0, min_snr=2):
        '''
        Find peaks in a Spectrum object and decompose specrum into components
        using a Gaussian kernel deconvolution technique. Most of this 
        functionality was adapted from https://github.com/lbl-anp/becquerel

        Parameters
        ----------
        spectrum : Spectrum object.
            previously initialized spectrum object.
        ref_x : int
            reference x-value (in channels) corresponding to ref_fwhm.
        ref_fwhm : int or float.
            fwhm value (in channels) corresponding to ref_x.
        fwhm_at_0 : int or float, optional
            fwhm value at channel = 0. The default is 1.0.
        min_snr : int or float, optional
            minimum SNR to look for releant peaks. The default is 2.

        Raises
        ------
        Exception
            'spectrum' must be a Spectrum object.

        Returns
        -------
        None.

        '''
        if type(spectrum) != sp.Spectrum:
            raise Exception("'spectrum' must be a Spectrum object")
        self.ref_x = ref_x
        self.ref_fwhm = ref_fwhm
        self.fwhm_at_0 = fwhm_at_0
        self.spectrum = spectrum
        self.min_snr = min_snr
        self.snr = []
        self.peak_plus_bkg = []
        self.bkg = []
        self.signal = []
        self.noise = []
        self.peaks_idx = []
        self.fwhm_guess = []
        self.calculate()

    def fwhm(self, x):
        '''
        Calculate the expected FWHM at the given x value

        Parameters
        ----------
        x : numpy array
            x-values.

        Returns
        -------
        numpy array.
            expected FWHM values.

        '''
        # f(x) = k * sqrt(x) + b
        # b = f(0)
        # k = f1/sqrt(x1)
        f0 = self.fwhm_at_0
        f1 = self.ref_fwhm
        x1 = self.ref_x
        # fwhm_sqr = np.sqrt(f0**2 + (f1**2 - f0**2) * (x / x1)**2)
        fwhm_sqr = (f1/np.sqrt(x1)) * np.sqrt(x) + f0
        return fwhm_sqr
    
    def kernel(self, x, edges):
        """Generate the kernel for the given x value."""
        fwhm1 = self.fwhm(x)
        sigma = fwhm1 / 2.355
        g1_x0 = gaussian_derivative(edges[:-1], x, sigma)
        g1_x1 = gaussian_derivative(edges[1:], x, sigma)
        kernel = g1_x0 - g1_x1
        return kernel
    
    def kernel_matrix(self, edges):
        """Build a matrix of the kernel evaluated at each x value."""
        n_channels = len(edges) - 1
        kern = np.zeros((n_channels, n_channels))
        for i, x in enumerate(edges[:-1]):
            kern[:, i] = self.kernel(x, edges)
        kern_pos = +1 * kern.clip(0, np.inf)
        kern_neg = -1 * kern.clip(-np.inf, 0)
        # normalize negative part to be equal to the positive part
        kern_neg *= kern_pos.sum(axis=0) / kern_neg.sum(axis=0)
        kmat = kern_pos - kern_neg
        return kmat
    
    def convolve(self, edges, data):
        """Convolve kernel with the data."""
        kern_mat = self.kernel_matrix(edges)
        kern_mat_pos = +1 * kern_mat.clip(0, np.inf)
        kern_mat_neg = -1 * kern_mat.clip(-np.inf, 0)
        peak_plus_bkg = np.dot(kern_mat_pos, data)
        bkg = np.dot(kern_mat_neg, data)
        signal = np.dot(kern_mat, data)
        noise = np.dot(kern_mat**2, data)
        #print("other")
        #noise = np.array([np.sqrt(x) for x in noise])
        noise = np.sqrt(noise)
        snr = np.zeros_like(signal)
        snr[noise > 0] = signal[noise > 0] / noise[noise > 0]
        return peak_plus_bkg, bkg, signal, noise, snr

    def calculate(self):
        """Calculate the convolution of the spectrum with the kernel."""
        
        snr = np.zeros(len(self.spectrum.counts))
        edg = np.append(self.spectrum.channels, self.spectrum.channels[-1]+1)
        # calculate the convolution
        peak_plus_bkg, bkg, signal, noise, snr = \
            self.convolve(edg, self.spectrum.counts)
        # find peak indices
        peaks_idx = find_peaks(snr.clip(0), height=self.min_snr)[0]
        
        self.fwhm_guess = self.fwhm(peaks_idx)
        self.peak_plus_bkg = peak_plus_bkg
        self.bkg = bkg
        self.signal = signal
        self.noise = noise
        self.snr = snr.clip(0)
        self.peaks_idx = peaks_idx
        #self.reset()
        
    def plot_kernel(self):
        """Plot the 3D matrix of kernels evaluated across the x values."""
        #edges = self.spectrum.channels
        edges = np.append(self.spectrum.channels, self.spectrum.channels[-1]+1)
        n_channels = len(edges) - 1
        kern_mat = self.kernel_matrix(edges)
        kern_min = kern_mat.min()
        kern_max = kern_mat.max()
        kern_min = min(kern_min, -1 * kern_max)
        kern_max = max(kern_max, -1 * kern_min)
        
        plt.figure()
        plt.imshow(
            kern_mat.T[::-1, :], cmap=plt.get_cmap('bwr'),
            vmin=kern_min, vmax=kern_max,
            extent=[n_channels, 0, 0, n_channels])
        plt.colorbar()
        plt.xlabel('Input x')
        plt.ylabel('Output x')
        plt.gca().set_aspect('equal')
        plt.title("Kernel Matrix")
        
    def plot_peaks(self, yscale='log', snrs="on", fig=None, ax=None):
        '''
        Plot spectrum and their found peak positions.

        Parameters
        ----------
        scale : string, optional
            Either 'log' or 'linear'. The default is 'log'.

        Returns
        -------
        None.

        '''
        plt.rc("font", size=14)  
        plt.style.use("seaborn-darkgrid")
        if self.spectrum.energies is None:
            #x = self.spectrum.channels[:-1]
            x = self.spectrum.channels
        else:
            x = self.spectrum.energies
        if fig is None:
            fig = plt.figure(figsize=(10,6))
        if ax is None:
            ax = fig.add_subplot()
        
        if snrs == "on":
            ax.plot(x, self.snr, label="SNR all")
        ax.plot(x, self.spectrum.counts, label="Raw spectrum")
        if yscale == 'log':
            ax.set_yscale("log")
        else:
            ax.set_yscale("linear")
        for xc in self.peaks_idx:
            if self.spectrum.energies is None:
                x0 = xc
            else:
                x0 = self.spectrum.energies[xc]
            ax.axvline(x=x0, color='red', linestyle='-', alpha=0.2)
        ax.legend(loc=1)
        ax.set_title(f"SNR > {self.min_snr}")
        ax.set_ylim(1e-1)
        ax.set_ylabel("Cts")
        ax.set_xlabel(self.spectrum.x_units)
        #plt.style.use("default")
    
    def plot_components(self, yscale='log'):
        '''
        Plot spectrum components after decomposition.

        Parameters
        ----------
        yscale : string, optional
            Either 'log' or 'linear'. The default is 'log'.

        Returns
        -------
        None.

        '''
        if self.spectrum.energies is None:
            x = self.spectrum.channels
        else:
            x = self.spectrum.energies
        plt.rc("font", size=14) 
        plt.style.use("seaborn-darkgrid")
        plt.figure(figsize=(10,6))
        plt.plot(x, self.spectrum.counts, label='Raw spectrum')
        plt.plot(x, self.peak_plus_bkg.clip(1e-1), label='Peaks+Continuum')
        plt.plot(x, self.bkg.clip(1e-1), label='Continuum')
        plt.plot(x, self.signal.clip(1e-1), label='Peaks')
        plt.plot(x, self.noise.clip(1e-1), label='noise')
        if yscale == "log":
            plt.yscale("log")
        else:
            plt.yscale("linear")
        #plt.xlim(0, len(spec))
        plt.ylim(3e-1)
        plt.xlabel(self.spectrum.x_units)
        plt.ylabel('Cts')
        plt.legend(loc=1)
        plt.style.use("default")

        
     
    
   