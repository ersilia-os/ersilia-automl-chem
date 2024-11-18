import os
import json
import shutil

from .. import ZairaBase, create_session_symlink

from .files import ParametersFile
from .files import SingleFile
from .files import ReferenceFile
from .standardize import Standardize
from .folding import Folds
from .tasks import SingleTasks
from .merge import DataMerger
from .clean import SetupCleaner
from .check import SetupChecker

from . import PARAMETERS_FILE, RAW_INPUT_FILENAME, RAW_REFERENCE_FILENAME

from ..vars import DATA_SUBFOLDER
from ..vars import DESCRIPTORS_SUBFOLDER
from ..vars import ESTIMATORS_SUBFOLDER
from ..vars import POOL_SUBFOLDER
from ..vars import LITE_SUBFOLDER
from ..vars import INTERPRETABILITY_SUBFOLDER
from ..vars import APPLICABILITY_SUBFOLDER
from ..vars import REPORT_SUBFOLDER
from ..vars import DISTILL_SUBFOLDER
from ..vars import OUTPUT_FILENAME
from ..vars import PRESETS_FILENAME

from ..tools.melloddy.pipeline import MelloddyTunerTrainPipeline
from ..augmentation.augment import Augmenter
from ..utils.pipeline import PipelineStep, SessionFile


class TrainSetup(object):
    def __init__(
        self,
        input_file,
        reference_file,
        output_dir,
        time_budget,
        task,
        threshold,
        direction,
        parameters,
        is_lazy,
        augment,
    ):
        if output_dir is None:
            output_dir = input_file.split(".")[0]
        if task is None and threshold is not None:
            task = "classification"
        else:
            if task is None:
                task = "regression"
        assert task in ["regression", "classification"]
        passed_params = {
            "time_budget": time_budget,
            "threshold": threshold,
            "direction": direction,
            "task": task,
        }
        self._is_lazy = is_lazy
        if self._is_lazy:
            passed_params["presets"] = "lazy"
        else:
            passed_params["presets"] = "standard"
        self.augment = augment
        if self.augment:
            passed_params["augment"] = True
        else:
            passed_params["augment"] = False
        self.params = self._load_params(parameters, passed_params)
        self.input_file = os.path.abspath(input_file)
        self.reference_file = reference_file
        if reference_file is not None:
            self.reference_file = os.path.abspath(reference_file)
        self.output_dir = os.path.abspath(output_dir)
        self.time_budget = time_budget  # TODO

    def is_lazy(self):
        with open(
            os.path.join(self.output_dir, DATA_SUBFOLDER, PRESETS_FILENAME), "w"
        ) as f:
            data = {"is_lazy": self._is_lazy}
            json.dump(data, f, indent=4)
        return self._is_lazy

    def _copy_input_file(self):
        extension = self.input_file.split(".")[-1]
        shutil.copy(
            self.input_file,
            os.path.join(self.output_dir, RAW_INPUT_FILENAME + "." + extension),
        )

    def _copy_reference_file(self):
        if self.reference_file is not None:
            extension = self.reference_file.split(".")[-1]
            shutil.copy(
                self.reference_file,
                os.path.join(self.output_dir, RAW_REFERENCE_FILENAME + "." + extension),
            )

    def _load_params(self, params, passed_params):
        return ParametersFile(full_path=params, passed_params=passed_params).load()

    def _save_params(self):
        with open(
            os.path.join(self.output_dir, DATA_SUBFOLDER, PARAMETERS_FILE), "w"
        ) as f:
            json.dump(self.params, f, indent=4)

    def _make_output_dir(self):
        if os.path.exists(self.output_dir):
            shutil.rmtree(self.output_dir)
        os.makedirs(self.output_dir)

    def _open_session(self):
        sf = SessionFile(self.output_dir)
        sf.open_session(
            mode="fit", output_dir=self.output_dir, model_dir=self.output_dir
        )
        create_session_symlink(self.output_dir)

    def _make_subfolder(self, name):
        os.makedirs(os.path.join(self.output_dir, name))

    def _make_subfolders(self):
        self._make_subfolder(DATA_SUBFOLDER)
        self._make_subfolder(DESCRIPTORS_SUBFOLDER)
        self._make_subfolder(ESTIMATORS_SUBFOLDER)
        self._make_subfolder(POOL_SUBFOLDER)
        self._make_subfolder(LITE_SUBFOLDER)
        self._make_subfolder(INTERPRETABILITY_SUBFOLDER)
        self._make_subfolder(APPLICABILITY_SUBFOLDER)
        self._make_subfolder(REPORT_SUBFOLDER)
        self._make_subfolder(DISTILL_SUBFOLDER)

    def _normalize_input(self):
        step = PipelineStep("normalize_input", self.output_dir)
        if not step.is_done():
            f = SingleFile(self.input_file, self.params)
            f.process()
            step.update()

    def _melloddy_tuner_run(self):
        step = PipelineStep("mellody_tuner", self.output_dir)
        if not step.is_done():
            MelloddyTunerTrainPipeline(
                os.path.join(self.output_dir, DATA_SUBFOLDER)
            ).run()
            step.update()

    def _standardize(self):
        step = PipelineStep("standardize", self.output_dir)
        if not step.is_done():
            Standardize(os.path.join(self.output_dir, DATA_SUBFOLDER)).run()
            step.update()

    def _process_reference_file(self):
        step = PipelineStep("reference_file", self.output_dir)
        if not step.is_done():
            f = ReferenceFile(self.output_dir)
            f.process()
            step.update()

    def _folds(self):
        step = PipelineStep("folds", self.output_dir)
        if not step.is_done():
            Folds(os.path.join(self.output_dir, DATA_SUBFOLDER)).run()
            step.update()

    def _tasks(self):
        step = PipelineStep("tasks", self.output_dir)
        if not step.is_done():
            SingleTasks(os.path.join(self.output_dir, DATA_SUBFOLDER)).run()
            step.update()

    def _merge(self):
        step = PipelineStep("merge", self.output_dir)
        if not step.is_done():
            DataMerger(os.path.join(self.output_dir, DATA_SUBFOLDER)).run()
            step.update()

    def _augment(self):
        if self.is_lazy():
            return
        if not self.augment:
            return
        step = PipelineStep("augment", self.output_dir)
        if not step.is_done():
            Augmenter(self.output_dir).run()
            step.update()

    def _clean(self):
        step = PipelineStep("clean", self.output_dir)
        if not step.is_done():
            SetupCleaner(os.path.join(self.output_dir, DATA_SUBFOLDER)).run()
            step.update()

    def _check(self):
        step = PipelineStep("setup_check", self.output_dir)
        if not step.is_done():
            SetupChecker(self.output_dir).run()
            step.update()

    def _initialize(self):
        step = PipelineStep("initialize", self.output_dir)
        if not step.is_done():
            self._make_output_dir()
            self._open_session()
            self._make_subfolders()
            self._save_params()
            self._copy_input_file()
            self._copy_reference_file()
            step.update()

    def update_elapsed_time(self):
        ZairaBase().update_elapsed_time()

    def is_done(self):
        if os.path.exists(os.path.join(self.output_dir, OUTPUT_FILENAME)):
            return True
        else:
            return False

    def setup(self):
        self._initialize()
        self._normalize_input()
        self._melloddy_tuner_run()
        self._standardize()
        self._process_reference_file()
        self._folds()
        self._tasks()
        self._merge()
        self._augment()
        self._clean()
        self._check()
        self.update_elapsed_time()
