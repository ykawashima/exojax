"""Pseudo line generator

"""
import numpy as np
from exojax.spec.dit import npgetix
import tqdm
import jax.numpy as jnp
import warnings
from exojax.utils.constants import hcperk
from exojax.spec.hitran import SijT


def plg_elower_addcon(indexa,Na,cnu,indexnu,nu_grid,mdb,elower_grid=None,Nelower=10,Ncrit=0,reshape=False, weedout=False, Tpred=296., preov=0., coefTpred=1.):
    """Pseudo Line Grid for elower w/ an additional condition
    
    Args:
       indexa: the indexing of the additional condition
       Na: the number of the additional condition grid
       cnu: contribution of wavenumber for LSD
       indexnu: nu index
       nugrid: nu grid
       mdb: molecular database (instance made by the MdbExomol/MdbHit class in moldb.py)
       elower_grid: elower_grid (optional)
       Nelower: # of division of elower between min to max values (when elower_grid is not given)
       Ncrit: frrozen line number per bin
       reshape: reshaping output arrays
       weedout: Is it ok to remove weakest lines or not?
       Tpred: guess of typical temperature in the atmosphere
       preov: ad hoc parameter to prevent overflow

    Returns:
       qlogsij0: pseudo logsij0
       qcnu: pseudo cnu
       num_unique: number of lines in grids
       elower_grid: elower of pl
       frozen_mask: mask for frozen lines into pseudo lines 
       nonzeropl_mask: mask for pseudo-lines w/ non-zero

    """
    elower = mdb.elower
    Nnugrid=len(nu_grid)
    Tref = 296.0
    Tpredrev = Tpred * coefTpred
    preov = max(- hcperk*(elower/Tpredrev - elower/Tref)) - 80. if preov==0. else preov
    #kT0=10000.0
    warnings.simplefilter('error')
    try:
        expme = np.exp(- hcperk*(elower/Tpredrev - elower/Tref) - preov)
    except RuntimeWarning as e:
        raise Exception(str(e)+' :\t Please adjust "preov"...')
    if elower_grid is None:
        margin = 1.0
        min_expme = np.exp(- hcperk*((min(elower)-margin)/Tpredrev - (min(elower)-margin)/Tref) - preov)
        max_expme = np.exp(- hcperk*((max(elower)+margin)/Tpredrev - (max(elower)+margin)/Tref) - preov)
        expme_grid = np.linspace(min_expme, max_expme, Nelower)
        elower_grid = (np.log(expme_grid) + preov) / (-hcperk) / (1/Tpredrev - 1/Tref)
    else:
        expme_grid=np.exp(-elower_grid/kT0)
        Nelower=len(expme_grid)
    warnings.simplefilter('default')

    qlogsij0,qcnu,num_unique,frozen_mask=get_qlogsij0_addcon(indexa,Na,cnu,indexnu,Nnugrid,mdb,expme,expme_grid,Ncrit=Ncrit, Tpred=Tpred) #, elower_grid=elower_grid, Nelower=10
    
    nonzeropl_mask=qlogsij0>-np.inf
    '''if weedout:
        qlogsij0_tr = np.log(np.exp(qlogsij0))
        nonzeropl_mask=(qlogsij0_tr>-np.inf) & (qlogsij0_tr<0)
    else:
        nonzeropl_mask = qlogsij0<0'''
    
    Nline=len(elower)
    Nunf=np.sum(~frozen_mask)
    Npl=len(qlogsij0[nonzeropl_mask])
    print("# of original lines:",Nline)        
    print("# of unfrozen lines:",Nunf)
    print("# of frozen lines:",np.sum(frozen_mask))
    print("# of pseudo lines:",Npl)
    print("# of total lines:",(Npl+Nunf))
    print("# compression:",(Npl+Nunf)/Nline)

    if reshape==True:
        qlogsij0=qlogsij0.reshape(Na,Nnugrid,Nelower)
        qcnu=qcnu.reshape(Na,Nnugrid,Nelower)
        num_unique=num_unique.reshape(Na,Nnugrid,Nelower)
        
    return qlogsij0,qcnu,num_unique,elower_grid,frozen_mask,nonzeropl_mask

def get_qlogsij0_addcon(indexa,Na,cnu,indexnu,Nnugrid,mdb,expme,expme_grid, Ncrit=0, Tpred=296.):
    """gather (freeze) lines w/ additional indexing

    Args:
       indexa: the indexing of the additional condition
       Na: the number of the additional condition grid
       cnu: contribution of wavenumber for LSD
       indexnu: index of wavenumber
       Nnugrid: number of nu grid
       mdb: molecular database (instance made by the MdbExomol/MdbHit class in moldb.py)
       expme: exp(-elower/kT0)
       expme_grid: exp(-elower/kT0)_grid
       Ncrit: frrozen line number per bin
       Tpred: guess of typical temperature in the atmosphere

    """
    threshold_persist_freezing = 10000
    m=len(expme_grid)
    n=m*Nnugrid
    Ng=n*Na
    
    cont,index=npgetix(expme,expme_grid) #elower contribution and elower index of lines
    eindex=index+m*indexnu+n*indexa #extended index elower,nu,a
    
    #frozen criterion
    num_unique=np.bincount(eindex,minlength=Ng) # number of the lines in a bin
    
    lmask=(num_unique>=Ncrit)
    erange=range(0,Ng)
    frozen_eindex=np.array(erange)[lmask]
    frozen_mask=np.isin(eindex,frozen_eindex)
    
    SijTpred_frozen = SijT(Tpred, \
                    mdb.logsij0[frozen_mask], mdb.nu_lines[frozen_mask], mdb.elower[frozen_mask], \
                    qT=mdb.qr_interp(Tpred))
    persist_freezing = SijTpred_frozen < max(SijTpred_frozen) / threshold_persist_freezing
    index_persist_freezing = np.where(frozen_mask)[0][persist_freezing]
    frozen_mask = np.isin(np.arange(len(frozen_mask)), index_persist_freezing)
        
    Sij=np.exp(mdb.logsij0)
    #qlogsij0
    qlogsij0=np.bincount(eindex,weights=Sij*(1.0-cont)*frozen_mask,minlength=Ng)
    qlogsij0=qlogsij0+np.bincount(eindex+1,weights=Sij*cont*frozen_mask,minlength=Ng)
    qlogsij0=np.log(qlogsij0)

    '''#qlogsij0
    Tref = 296.0
    qlogsij0 = np.bincount(eindex, weights = \
                      (jnp.log(jnp.exp(logsij0 - hcperk*(elower/Tpred - elower/Tref)) * (1. - cont)) + \
                       hcperk*(elower_grid[index]/Tpred - elower_grid[index]/Tref) )*frozen_mask, minlength=Ng)
    qlogsij0 = qlogsij0 + np.bincount(eindex+1, weights = \
                      (jnp.log(jnp.exp(logsij0 - hcperk*(elower/Tpred - elower/Tref)) * (cont)) + \
                                  hcperk*(elower_grid[index+1]/Tpred - elower_grid[index+1]/Tref) )*frozen_mask, minlength=Ng)'''

    #qcnu
    qcnu_den=np.bincount(eindex,weights=Sij*frozen_mask,minlength=Ng)
    qcnu_den=qcnu_den+np.bincount(eindex+1,weights=Sij*frozen_mask,minlength=Ng)
    qcnu_den[qcnu_den==0.0]=1.0
    
    qcnu_num=np.bincount(eindex,weights=Sij*cnu*frozen_mask,minlength=Ng)
    qcnu_num=qcnu_num+np.bincount(eindex+1,weights=Sij*cnu*frozen_mask,minlength=Ng)
    qcnu=qcnu_num/qcnu_den

    return qlogsij0,qcnu,num_unique,frozen_mask

def plg_elower(cnu,indexnu,Nnugrid,logsij0,elower,elower_grid=None,Nelower=10,Ncrit=0,reshape=True):
    """Pseudo Line Grid for elower
    
    Args:
       cnu: contribution of wavenumber for LSD
       indexnu: index of wavenumber
       Nnugrid: number of Ngrid
       logsij0: log line strength
       elower: elower
       elower_grid: elower_grid (optional)
       Nelower: # of division of elower between min to max values when elower_grid is not given
       Ncrit: frrozen line number per bin

    Returns:
       qlogsij0
       qcnu
       num_unique
       elower_grid

    """
    
    kT0=10000.0
    expme=np.exp(-elower/kT0)
    if elower_grid is None:
        margin=1.0
        min_expme=np.min(expme)*np.exp(-margin/kT0)
        max_expme=np.max(expme)*np.exp(margin/kT0)
        expme_grid=np.linspace(min_expme,max_expme,Nelower)
        elower_grid=-np.log(expme_grid)*kT0
    else:
        expme_grid=np.exp(-elower_grid/kT0)
        Nelower=len(expme_grid)
        
    qlogsij0,qcnu,num_unique,frozen_mask=get_qlogsij0(cnu,indexnu,Nnugrid,logsij0,expme,expme_grid,Nelower=10,Ncrit=Ncrit)

    if reshape==True:
        qlogsij0=qlogsij0.reshape(Nnugrid,Nelower)
        qcnu=qcnu.reshape(Nnugrid,Nelower)
        num_unique=num_unique.reshape(Nnugrid,Nelower)
    
    print("# of unfrozen lines:",np.sum(~frozen_mask))
    print("# of pseudo lines:",len(qlogsij0[qlogsij0>0.0]))
    
    return qlogsij0,qcnu,num_unique,elower_grid

def get_qlogsij0(cnu,indexnu,Nnugrid,logsij0,expme,expme_grid,Nelower=10,Ncrit=0):
    """gather (freeze) lines

    Args:
       cnu: contribution of wavenumber for LSD
       indexnu: index of wavenumber
       logsij0: log line strength
       expme: exp(-elower/kT0)
       expme_grid: exp(-elower/kT0)_grid
       Nelower: # of division of elower between min to max values

    """
    m=len(expme_grid)
    cont,index=npgetix(expme,expme_grid) #elower contribution and elower index of lines
    eindex=index+m*indexnu #extended index
    
    #frozen criterion
    Ng=m*Nnugrid
    num_unique=np.bincount(eindex,minlength=Ng) # number of the lines in a bin
    
    lmask=(num_unique>=Ncrit)
    erange=range(0,Ng)
    frozen_eindex=np.array(erange)[lmask]
    frozen_mask=np.isin(eindex,frozen_eindex)
        
    Sij=np.exp(logsij0)
    #qlogsij0
    qlogsij0=np.bincount(eindex,weights=Sij*(1.0-cont)*frozen_mask,minlength=Ng)
    qlogsij0=qlogsij0+np.bincount(eindex+1,weights=Sij*cont*frozen_mask,minlength=Ng)    
    qlogsij0=np.log(qlogsij0)

    #qcnu
    qcnu_den=np.bincount(eindex,weights=Sij*frozen_mask,minlength=Ng)
    qcnu_den=qcnu_den+np.bincount(eindex+1,weights=Sij*frozen_mask,minlength=Ng)
    qcnu_den[qcnu_den==0.0]=1.0
    
    qcnu_num=np.bincount(eindex,weights=Sij*cnu*frozen_mask,minlength=Ng)
    qcnu_num=qcnu_num+np.bincount(eindex+1,weights=Sij*cnu*frozen_mask,minlength=Ng)
    qcnu=qcnu_num/qcnu_den

    return qlogsij0,qcnu,num_unique,frozen_mask


def diff_frozen_vs_pseudo(coefTpred_array, Tpred):
#if __name__ == "__main__":
    coefTpred = coefTpred_array[0]
    import numpy as np
    import jax.numpy as jnp
    from exojax.spec import moldb, contdb
    from exojax.spec.rtransfer import nugrid
    from exojax.spec import initspec
    import matplotlib.pyplot as plt
    import time
    import tqdm
    import pandas as pd
    import copy
    #    dats=pd.read_csv("Gl229B_spectrum_H2O.dat",names=("wav","flux"),delimiter="\s")
    #    wavmic=dats["wav"].values*1.e4
    #    ccgs=29979245800.0
    #    flux=dats["flux"].values*ccgs

    #plg_h2o_Tpred.py
    import sys
    sys.path.append('/home/tako/ghR/exojax/src/exojax/spec/')
    import plg_Tpred as plg


    #wls,wll = 15541, 15551
    #nus, wav, reso = nugrid(wls, wll, int((wll-wls)/nugrid_res), unit="AA", xsmode="modit")
    #nus,wav,reso = nugrid(15540.0,15560.0,2000,unit="AA",xsmode="modit")
    #nus,wav,reso = nugrid(16300.0,16600.0,10000,unit="AA",xsmode="modit") #test220409

    #mdb = moldb.MdbExomol('.database/H2O/1H2-16O/POKAZATEL/', nus, crit=1.e-40) #, Ttyp=4000)
    #mdb_orig = copy.deepcopy(mdb)
    mdb = copy.deepcopy(mdb_orig)
    print("Nline=",len(mdb.A))
    cdbH2H2 = contdb.CdbCIA('.database/H2-H2_2011.cia', nus)

    cnu, indexnu, R, pmarray = initspec.init_modit(mdb.nu_lines, nus)
    cnu_orig = copy.deepcopy(cnu)
    indexnu_orig = copy.deepcopy(indexnu)




    #make index_gamma
    gammaL_set=mdb.alpha_ref+mdb.n_Texp*(1j) #complex value
    gammaL_set_unique=np.unique(gammaL_set)
    Ngamma=np.shape(gammaL_set_unique)[0]
    index_gamma=np.zeros_like(mdb.alpha_ref,dtype=int)
    alpha_ref_grid=gammaL_set_unique.real
    n_Texp_grid=gammaL_set_unique.imag
    for j,a in tqdm.tqdm(enumerate(gammaL_set_unique)):
        index_gamma=np.where(gammaL_set==a,j,index_gamma)
    print("done.")
    #-------------------------------------------------------

    reshape=False
    ts=time.time()
    qlogsij0,qcnu,num_unique,elower_grid,frozen_mask,nonzeropl_mask=plg.plg_elower_addcon(index_gamma,Ngamma,cnu,indexnu,nus,
                                                                                              mdb,Ncrit=Ncrit,Nelower=Nelower,reshape=reshape,
                                                                                              Tpred=Tpred, coefTpred=coefTpred)
    te=time.time()
    print(te-ts,"sec")
    print("elower_grid",elower_grid)

    if reshape:
        num_unique=np.array(num_unique,dtype=float)
        num_unique[num_unique<Ncrit]=None
        fig=plt.figure(figsize=(10,4.5))
        ax=fig.add_subplot(311)
        c=plt.imshow(num_unique[0,:,:].T)
        #    c=plt.imshow(np.sum(num_unique[:,:,:],axis=0).T)
        plt.colorbar(c,shrink=0.2)
        ax.set_aspect(0.1/ax.get_data_ratio())
        ax=fig.add_subplot(312)
        c=plt.imshow(qlogsij0[0,:,:].T)
        plt.colorbar(c,shrink=0.2)
        ax.set_aspect(0.1/ax.get_data_ratio())
        plt.show()
        import sys
        sys.exit()
    Nnugrid=len(nus)

    mdb, cnu, indexnu=plg.gather_lines(mdb,Ngamma,Nnugrid,Nelower,nus,cnu,indexnu,qlogsij0,qcnu,elower_grid,alpha_ref_grid,n_Texp_grid,frozen_mask,nonzeropl_mask)

    ##
    from exojax.spec import rtransfer as rt
    from exojax.spec import dit, modit
    from exojax.spec.rtransfer import rtrun, dtauM, dtauCIA, nugrid
    from exojax.spec import planck, response
    from exojax.spec import molinfo


    #atm
    NP=100
    Parr, dParr, k=rt.pressure_layer(NP=NP)
    molmassH2O=molinfo.molmass("H2O")
    mmw=2.33 #mean molecular weight
    mmrH2=0.74
    molmassH2=molinfo.molmass("H2")
    vmrH2=(mmrH2*mmw/molmassH2) #VMR

    Pref=1.0 #bar
    ONEARR=np.ones_like(Parr)


    # Precomputing gdm_ngammaL
    from exojax.spec.modit import setdgm_exomol
    from jax import jit, vmap


    fT = lambda T0,alpha: T0[:,None]*(Parr[None,:]/Pref)**alpha[:,None]
    T0_test=np.array([Tpred-300.,Tpred+300.,Tpred-300.,Tpred+300.])
    alpha_test=np.array([0.2,0.2,0.05,0.05])
    res=0.2
    dgm_ngammaL=setdgm_exomol(mdb,fT,Parr,R,molmassH2O,res,T0_test,alpha_test)
    dgm_ngammaL_orig = setdgm_exomol(mdb_orig, fT, Parr, R, molmassH2O, res, T0_test, alpha_test)

    u1=0.0
    u2=0.0
    vsini=5.0

    def frun(Tarr,MMR_,Mp,Rp,u1,u2,RV,vsini):
        g=2478.57730044555*Mp/Rp**2
        SijM_,ngammaLM_,nsigmaDl_=modit.exomol(mdb,Tarr,Parr,R,molmassH2O)
        xsm_=modit.xsmatrix(cnu,indexnu,R,pmarray,nsigmaDl_,ngammaLM_,SijM_,nus,dgm_ngammaL)
        #abs is used to remove negative values in xsv
        dtaum=dtauM(dParr,jnp.abs(xsm_),MMR_*ONEARR,molmassH2O,g)
        #CIA
        dtaucH2H2=dtauCIA(nus,Tarr,Parr,dParr,vmrH2,vmrH2,mmw,g,cdbH2H2.nucia,cdbH2H2.tcia,cdbH2H2.logac)
        dtau=dtaum+dtaucH2H2
        sourcef = planck.piBarr(Tarr,nus)
        F0=rtrun(dtau,sourcef)
        Frot=response.rigidrot(nus,F0,vsini,u1,u2)
        #mu=response.ipgauss_sampling(nusd,nus,Frot,beta_inst,RV)
        mu=Frot
        return mu
    def frun_orig(Tarr, MMR_, Mp, Rp, u1, u2, RV, vsini):
        g = 2478.57730044555*Mp/Rp**2
        SijM_, ngammaLM_, nsigmaDl_ = modit.exomol(mdb_orig, Tarr, Parr, R, molmassH2O)
        xsm_ = modit.xsmatrix(cnu_orig, indexnu_orig, R, pmarray, nsigmaDl_, ngammaLM_, SijM_, nus, dgm_ngammaL_orig)
        #abs is used to remove negative values in xsv
        dtaum = dtauM(dParr, jnp.abs(xsm_), MMR_*ONEARR, molmassH2O, g)
        #CIA
        dtaucH2H2 = dtauCIA(nus, Tarr, Parr, dParr, vmrH2, vmrH2, mmw, g, cdbH2H2.nucia, cdbH2H2.tcia, cdbH2H2.logac)
        dtau = dtaum+dtaucH2H2
        sourcef  =  planck.piBarr(Tarr, nus)
        F0 = rtrun(dtau, sourcef)
        Frot = response.rigidrot(nus, F0, vsini, u1, u2)
        #mu = response.ipgauss_sampling(nusd, nus, Frot, beta_inst, RV)
        mu = Frot
        return mu
        
    Tarr = Tpred*(Parr/Pref)**0.1
    mu=frun(Tarr,MMR_=0.0059,Mp=33.2,Rp=0.88,u1=0.0,u2=0.0,RV=10.0,vsini=0.1)
    mu_orig = frun_orig(Tarr,MMR_=0.0059,Mp=33.2,Rp=0.88,u1=0.0,u2=0.0,RV=10.0,vsini=0.1)
                
        return abs(np.mean(mu - mu_orig))
        
        
def optimize_coefTpred(Tpred):
    import scipy.optimize as opt
    coefTpred_opt = opt.least_squares(\
    fun=sct.diff_frozen_pseudo, x0=[1.,], bounds=(0.5, 1.5), args=[Tpred,])
    return coefTpred_opt.x[0]

    
def gather_lines(mdb,Na,Nnugrid,Nelower,nu_grid,cnu,indexnu,qlogsij0,qcnu,elower_grid,alpha_ref_grid,n_Texp_grid,frozen_mask,nonzeropl_mask):
    """gather pseudo lines and unfrozen lines into lines for exomol

    Args:

       mdb: molecular database
       Na: the number of the additional condition grid (gammaL set for Exomol)
       Nnugrid: # of nu_grid
       Nelower: # of elower grid
       nu_grid: nu grid
       cnu: contribution of wavenumber for LSD
       indexnu: index nu
       qlogsij0: log line strength
       qcnu: pseudo line, contribution of wavenumber for LSD
       elower_grid: elower_grid
       alpha_ref_grid: grid of alpha_ref
       n_Texp_grid: grid of n_Texp
       frozen_mask: mask for frozen lines into pseudo lines 
       nonzeropl_mask: mask for pseudo-lines w/ non-zero

    Returns:
       mdb for the gathered lines
       cnu for the gathered lines
       indexnu for the gathered lines


    """
    
    
    #gathering
    ## q-part should be ((Na,Nnugrid,Nelower).flatten)[nonzeropl_mask]
    import jax.numpy as jnp

    ## MODIT
    arrone=np.ones((Na,Nelower))    
    qnu_grid=(arrone[:,np.newaxis,:]*nu_grid[np.newaxis,:,np.newaxis]).flatten()
    indexnu_grid=np.array(range(0,len(nu_grid)),dtype=int)
    qindexnu=(arrone[:,np.newaxis,:]*indexnu_grid[np.newaxis,:,np.newaxis]).flatten()
    cnu=np.hstack([qcnu[nonzeropl_mask],cnu[~frozen_mask]])
    indexnu=np.array(np.hstack([qindexnu[nonzeropl_mask],indexnu[~frozen_mask]]),dtype=int)
    
    #mdb
    mdb.logsij0=np.hstack([qlogsij0[nonzeropl_mask],mdb.logsij0[~frozen_mask]])
    mdb.nu_lines=np.hstack([qnu_grid[nonzeropl_mask],mdb.nu_lines[~frozen_mask]])
    mdb.dev_nu_lines=jnp.array(mdb.nu_lines)

    onearr=np.ones((Na,Nnugrid))
    qelower=(onearr[:,:,np.newaxis]*elower_grid[np.newaxis,np.newaxis,:]).flatten()
    mdb.elower=np.hstack([qelower[nonzeropl_mask],mdb.elower[~frozen_mask]])
    
    #gamma     #Na,Nnugrid,Nelower
    onearr_=np.ones((Nnugrid,Nelower))
    alpha_ref_grid=alpha_ref_grid[:,np.newaxis,np.newaxis]*onearr_
    alpha_ref_grid=alpha_ref_grid.flatten()
    n_Texp_grid=n_Texp_grid[:,np.newaxis,np.newaxis]*onearr_
    n_Texp_grid=n_Texp_grid.flatten()    
    mdb.alpha_ref=np.hstack([alpha_ref_grid[nonzeropl_mask],mdb.alpha_ref[~frozen_mask]])
    mdb.n_Texp=np.hstack([n_Texp_grid[nonzeropl_mask],mdb.n_Texp[~frozen_mask]])
    mdb.A=jnp.zeros_like(mdb.logsij0) #no natural width

    lenarr=[len(mdb.logsij0),len(mdb.elower),len(cnu),len(indexnu),len(mdb.nu_lines),len(mdb.dev_nu_lines),len(mdb.alpha_ref),len(mdb.n_Texp),len(mdb.A)]
    
    Ngat=np.unique(lenarr)
    if len(Ngat)>1:
        print("Error: Length mismatch")
    else:
        print("Nline gathered=",Ngat[0])
    
    return mdb, cnu, indexnu

    
