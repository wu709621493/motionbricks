"""Run with the DESNZ Coal_since_1853.xls path as the sole argument."""
import sys

import matplotlib.pyplot as plt
import numpy as np
import xlrd
from scipy.optimize import curve_fit
from scipy.special import expit

sheet = xlrd.open_workbook(sys.argv[1]).sheet_by_name("Coal Availability & Consumption")
# Rows 11–27 are disjoint ten-year averages. Column Q excludes overseas shipments.
means = np.array([sheet.cell_value(row, 16) for row in range(10, 27)])
ends = np.arange(1862, 2023, 10)
annual = np.array([sheet.cell_value(row, 16) for row in range(28, 141)])
years = np.arange(1913, 2026)
assert len(means) == len(ends) and len(annual) == len(years)
assert all(str(sheet.cell_value(i, 0)).startswith(str(y)) for i, y in enumerate(years, 28))
cumulative = np.cumsum(10 * means) / 1000  # Gt since end-1852
cut = 14  # last three complete decades held out

def logistic(t, height, rate, midpoint):
    return height * expit(rate * (t - midpoint))

def stock(t, height, rate, midpoint):
    return logistic(t, height, rate, midpoint) - logistic(1852, height, rate, midpoint)

def pulse(t, height, rate, midpoint):
    return 100 * (stock(t, height, rate, midpoint) - stock(t - 10, height, rate, midpoint))

def fit(fn, data, count, init, bounds):
    pars = curve_fit(fn, ends[:count], data[:count], p0=init, bounds=bounds, maxfev=50000)[0]
    return fn(ends, *pars), pars

fig, axes = plt.subplots(2, 1, figsize=(8, 7), constrained_layout=True)
for ax, data, models, unit in [
    (axes[0], means, [(pulse, 'single pulse', [25,.03,1930], ([0,.0001,1750],[500,.5,2150])),
                      (logistic, 'monotone S', [170,-.03,2000], ([0,-.5,1750],[1000,.5,2200]))], 'Million tonnes / year'),
    (axes[1], cumulative, [(stock, 'logistic', [23,.03,1930], ([0,.0001,1750],[500,.5,2150]))], 'Billion tonnes since 1852')]:
    ax.plot(ends,data,'ko',ms=4,label='Observed decade blocks')
    for fn,label,init,bounds in models:
        # Try both directions for the monotone curve and choose the training optimum.
        def best(n):
            opts = [fit(fn,data,n,init,bounds)]
            if fn is logistic:
                opts.append(fit(fn,data,n,[170,.03,1880],bounds))
            return min(opts,key=lambda p: np.sum((p[0][:n]-data[:n])**2))
        pred,pars = best(len(data))
        held,_ = best(cut)
        print(label, 'R2',1-np.sum((pred-data)**2)/np.sum((data-data.mean())**2),
              'holdout RMSE',np.mean((held[cut:]-data[cut:])**2)**.5, 'parameters',pars)
        ax.plot(ends,pred,label=label+' (all blocks)')
        ax.plot(ends[cut-1:],held[cut-1:],'--',label=label+' (fit through 1992)')
    linear = np.polyval(np.polyfit(ends[:cut],data[:cut],1),ends[cut:])
    print('linear holdout RMSE', np.mean((linear-data[cut:])**2)**.5)
    ax.axvspan(1992,2022,color='grey',alpha=.1)
    ax.set_ylabel(unit)
    ax.legend(fontsize=8)
axes[0].plot(years,annual,color='grey',alpha=.38,lw=.8,label='Annual observations (1913–2025)')
axes[0].legend(fontsize=8)
axes[0].set_title('UK inland coal consumption')
axes[1].set_xlabel('Year (decade blocks plotted at end year)')
fig.savefig('uk-coal-fit.svg')
print('observed cumulative through 2022', cumulative[-1], '2023–25 annual',annual[-3:])

# Independent sensitivity check using only measured calendar years.
for fn, name, init, bounds in [
    (logistic, 'annual monotone S', [200,-.04,1980], ([0,-1,1750],[1000,1,2200])),
    (lambda t,h,r,m: 1000*(stock(t,h,r,m)-stock(t-1,h,r,m)),
     'annual single pulse',[25,.03,1930],([0,.0001,1750],[500,.5,2150]))]:
    for n in (len(years), len(years)-20):
        pars = curve_fit(fn,years[:n],annual[:n],p0=init,bounds=bounds,maxfev=50000)[0]
        prediction = fn(years,*pars)
        if n == len(years):
            print(name,'annual R2',1-np.sum((prediction-annual)**2)/np.sum((annual-annual.mean())**2))
        else:
            print(name,'2006–2025 RMSE',np.mean((prediction[n:]-annual[n:])**2)**.5)
