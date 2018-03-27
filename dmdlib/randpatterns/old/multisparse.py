import numpy as np
from dmdlib.randpatterns.utils import run_presentations, parser
from dmdlib.randpatterns.old.sparsenoise import sparsenoise_function_generator
import os
if os.name == 'nt':
    appdataroot = os.environ['APPDATA']
    appdatapath = os.path.join(appdataroot, 'dmdlib')


def main():
    parser.description = 'Sparsenoise stimulus generator.'
    parser.add_argument('fraction_on', type=float, nargs='*',
                        help='fraction of pixels on per presentation frame (between 0 and 1)')
    parser.add_argument('--frames_per_run', type=int, help='number of frames per run presentation', default=60000)
    args = parser.parse_args()
    fracs = args.fraction_on
    frames_total = args.nframes
    frames_per_run = args.frames_per_run
    n_runs = -(-frames_total // frames_per_run)  # ceiling division.
    assert n_runs > len(fracs)
    if n_runs > (frames_total // frames_per_run):
        print('WARNING: {} frames were requested, but {} frames will be presented due to rounding.'.format(
            frames_total, n_runs * frames_per_run
        ))
    if n_runs < len(fracs) * 2:
        print('WARNING: each sparsity fraction will be presented in only one contiguous run of {} frames'.format(frames_per_run))
    runs_per_frac = -(-n_runs // len(fracs))  # ceiling division
    print('Running each sparsity fraction {} times...'.format(runs_per_frac))
    frac_list_weighted = []
    for frac in fracs:  # check to make sure fractions are valid.
        if frac > 1. or frac < 0.:
            errst = 'Fraction argument must be between 0 and 1.'
            raise ValueError(errst)
        else:
            frac_list_weighted.extend([frac] * runs_per_frac)
    frac_list_permuted = np.random.permutation(frac_list_weighted)
    savefile_base, _ = os.path.splitext(args.savefile)
    presented = 0
    for i in range(n_runs):
        savefile_str = "{}_r{:03d}.h5".format(savefile_base, i)
        print('Starting run number {} of {}.'.format(i+1, n_runs))
        frac = frac_list_permuted[i]
        seq_gen = sparsenoise_function_generator(frac)
        presented += frames_per_run
        run_presentations(frames_per_run, savefile_str, seq_gen, file_overwrite=args.overwrite,
                          seq_debug=False, image_scale=args.scale, picture_time=args.pic_time, mask_filepath=args.maskfile)

if __name__ == '__main__':
    import os
    main()
