import math
import os
import sys
from bisect import bisect_left
from collections.abc import Iterable
from queue import Queue

import numpy as np

from hls4ml.backends import FPGABackend
from hls4ml.model.flow import register_flow
from hls4ml.model.optimizer import get_backend_passes
from hls4ml.report import parse_vivado_report


class SymbolicExpressionBackend(FPGABackend):
    def __init__(self):
        super().__init__('SymbolicExpression')
        self._register_flows()

    def _register_flows(self):
        vivado_types = [
            'vivado:transform_types',
        ]
        vivado_types_flow = register_flow('specific_types', vivado_types, requires=None, backend=self.name)

        templates = self._get_layer_templates()
        template_flow = register_flow('apply_templates', self._get_layer_templates, requires=None, backend=self.name)

        writer_passes = ['make_stamp', 'symbolicexpression:write_hls']
        self._writer_flow = register_flow('write', writer_passes, requires=['vivado:ip'], backend=self.name)

        all_passes = get_backend_passes(self.name)

        ip_flow_requirements = [vivado_types_flow, template_flow]
        ip_flow_requirements = list(filter(None, ip_flow_requirements))

        self._default_flow = register_flow('ip', None, requires=ip_flow_requirements, backend=self.name)

    def get_default_flow(self):
        return self._default_flow

    def get_writer_flow(self):
        return self._writer_flow

    def create_initial_config(
        self,
        part='xcvu9p-flga2577-2-e',
        clock_period=5,
        io_type='io_parallel',
        compiler='vivado_hls',
        hls_include_path=None,
        hls_libs_path=None,
    ):
        config = {}

        config['Part'] = part if part is not None else 'xcvu9p-flga2577-2-e'
        config['ClockPeriod'] = clock_period
        config['IOType'] = io_type
        config['Compiler'] = compiler if compiler is not None else 'vivado_hls'
        if not all([hls_include_path, hls_libs_path]):
            # Try to infer the include path from Vivado path
            bin_path = os.popen(f'command -v {compiler}').read().strip()
            if hls_include_path is None:
                hls_include_path = bin_path.replace(f'/bin/{compiler}', '/include')
                if not os.path.exists(hls_include_path + '/hls_math.h'):
                    raise Exception(
                        'Vivado HLS header files not found. Make sure you pass the proper path to the "include" directory (for example "/opt/Xilinx/Vivado/2020.1/include").'
                    )
            if hls_libs_path is None:
                hls_libs_path = bin_path.replace(f'/bin/{compiler}', '/lnx64')
                if not os.path.exists(hls_libs_path + '/lib/csim/libhlsmc++-GCC46.so'):
                    raise Exception(
                        'Vivado HLS libraries not found. Make sure you pass the proper path to the "lnx64" directory (for example "/opt/Xilinx/Vivado/2020.1/lnx64").'
                    )
        config['HLSIncludePath'] = hls_include_path
        config['HLSLibsPath'] = hls_libs_path
        config['HLSConfig'] = {}

        return config

    def build(self, model, reset=False, csim=True, synth=True, cosim=False, validation=False, export=False, vsynth=False):
        if 'linux' in sys.platform:
            found = os.system('command -v vivado_hls > /dev/null')
            if found != 0:
                raise Exception('Vivado HLS installation not found. Make sure "vivado_hls" is on PATH.')

        curr_dir = os.getcwd()
        os.chdir(model.config.get_output_dir())
        os.system(
            'vivado_hls -f build_prj.tcl "reset={reset} csim={csim} synth={synth} cosim={cosim} validation={validation} export={export} vsynth={vsynth}"'.format(
                reset=reset, csim=csim, synth=synth, cosim=cosim, validation=validation, export=export, vsynth=vsynth
            )
        )
        os.chdir(curr_dir)

        return parse_vivado_report(model.config.get_output_dir())
