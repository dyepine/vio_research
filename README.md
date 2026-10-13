# VIO research

Подготовка и запуск используют стандартный lifecycle VSLAM-LAB.
План и состояние переезда: [docs/dataset-migration.md](docs/dataset-migration.md).

## Чистая машина

Поддерживается Linux x86_64; нужны `git`, `make`, `curl`, `tar`, `sha256sum`
(обычные системные утилиты). Системный ROS и ручная установка Python-пакетов не нужны.
После checkout репозитория:

```bash
make prepare
make run
```

`make prepare` сам инициализирует закреплённый submodule, устанавливает локальный
Pixi 0.81.0 с проверкой SHA-256 и окружения из `pixi.lock`,
скачивает и готовит **все четыре выбранные записи**:
GrandTour `kaeb_1`, `alb_1`; BotanicGarden `1018_00`, `1018_13` вместе с corrected GT.
Список — `configs/datasets/selected.yaml`. Каталог адаптера содержит все 10 публичных
BotanicGarden-записей с bags и corrected GT: `1005_00`, `1005_01`, `1005_05`,
`1005_07`, `1006_01`, `1006_03`, `1008_01`, `1008_03`, `1018_00`, `1018_13`.
Расширение каталога не расширяет выбор для скачивания: у нас остаются две `1018`-записи.
Чтобы выбрать другую опубликованную запись, укажите её в selection YAML.
Для трёх дополнительных bags checksum — SHA-256 из OneDrive metadata;
для остальных bags и corrected GT сохранены MD5. Другие 23 записи авторы
предоставляют по запросу, публичные download URLs для них не указаны. `lmb_2`, `hoeb_1` и прежняя `alb_2`
не включены в основной набор.

По умолчанию данные лежат в `$HOME/datasets/vio_research`. Для SSD:

```bash
VIO_DATA_DIR=/path/to/ssd/vio_research/data make prepare
VIO_DATA_DIR=/path/to/ssd/vio_research/data make run
```

Пути можно сохранить в `.envrc`, которую `make` создаёт и не перезаписывает.
Локальная `.envrc` этой машины уже указывает на `/media/napalkov/T7/vio_research/data`.
`BOTANICGARDEN_SOURCE_DIR` позволяет переиспользовать скачанные bags/GT; `.part`
докачивается на месте. Bags и corrected GT скачиваются сразу с официального
OneDrive, без обращений к SJTU. Подписанный download URL обновляется при каждой
попытке. Обрывы допускаются, пока сохранённый файл растёт; 10 ошибок подряд
без прогресса останавливают загрузку с сохранением `.part`.
Полный размер и MD5 обязательны. Повтор той же команды не требует ручного распаковывания.
В терминале `make prepare` показывает `tqdm` progress bar: процент, объём, скорость
и ETA. При докачке учитывается сохранённая часть; проверка MD5 имеет отдельный
индикатор. При перенаправлении в файл динамические бары отключены, остаются
сообщения о запросах, ошибках и завершении.
Доступность и скорость внешних зеркал остаются ограничением.

Адаптер BotanicGarden и необходимые исправления ROS/download helpers находятся
в нашем [fork VSLAM-LAB](https://github.com/dyepine/VSLAM-LAB/tree/vio-research-datasets).
Submodule закреплён на commit `65e7eac788eb4c2d44f15658c58b3564b10c3da7`;
ветка fork — `vio-research-datasets`. Чистый checkout сразу содержит адаптер,
патч и его применение при bootstrap удалены. Bootstrap читает pin из Git,
при несовпадении ревизии сохраняет checkout и останавливается.
Исходный `VSLAM-LAB/VSLAM-LAB` остаётся источником обновлений. Отправка PR
в upstream не входит в эту работу. Обновление fork и pin требует проверки
совместимости адаптера и повторного запуска тестов.

## Конфигурация и запуск

`configs/datasets/selected.yaml` — список скачиваемых записей в штатном формате
VSLAM-LAB `dataset: [sequence, ...]`. Его читают `make prepare`, `make plan` и
`make validate`. Запас места — 15 GB, лимит каталога данных — 125 GB;
проверка места не резервирует диск. При подготовке по файлу эксперимента можно
переопределить бюджеты через необязательный `Preparation: {reserve_gb: 15, max_data_gb: 125}`.

`configs/experiments/comparison.yaml` — один файл эксперимента:

```yaml
Datasets:
  grandtour-alphasense: [kaeb_1]
  botanicgarden: ['1018_00']
Methods:
  orbslam3_default:
    Module: orbslam3
    Parameters: {mode: stereo-vi, verbose: 0}
  orbslam3_no_loop:
    Module: orbslam3
    Parameters: {mode: stereo-vi, verbose: 0}
    Settings: {loopClosing: 0}
NumRuns: 1
Evaluation:
  align: SE3
  correct_scale: false
  max_time_difference_s: 0.01
```

Каждый вариант `Methods` запускается на каждой записи `Datasets` с `NumRuns`
повторами. В примере — четыре запуска. Варианты имеют отдельные логи и результаты.
`Parameters` — параметры запуска VSLAM-LAB; `Settings` переопределяет только
указанные ключи штатного YAML метода. Калибровка камер/IMU берётся из датасета.
Без `Settings` применяется штатный файл метода. Viewer по умолчанию выключен
(`verbose: 0`); при первом запуске VSLAM-LAB устанавливает метод и vocabulary/weights.

```bash
make methods                                  # каталог методов
make run                                      # вся матрица comparison.yaml
make run CONFIG=configs/experiments/comparison.yaml
make run RGB_MAX=200                           # короткая проверка всей матрицы
make run PLAN=1                                # native YAML без запуска методов
make plan                                     # место для selected.yaml
make prepare CONFIG=configs/experiments/comparison.yaml # только записи эксперимента
make validate CONFIG=configs/experiments/comparison.yaml
```

`METHOD`/`MODE` перенесены в файл эксперимента. Без `CONFIG` подготовка читает
`VIO_DATASET_CONFIG` (`selected.yaml`), запуск — `VIO_EXPERIMENT_CONFIG`
(`comparison.yaml`). Машинные пути остаются в `.envrc`.
`run_catalog.py` проверяет подготовленные входы и окно IMU, генерирует native YAML,
затем вызывает штатные `run_exp`/`run_sequence`. Исходный файл эксперимента,
эффективные настройки всех вариантов, протокол оценки и аудит входов сохраняются
в `${VIO_RESULTS_DIR}/VSLAM-LAB-Evaluation/comparison_.../inputs/`.
`PLAN=1` может установить метод для получения его штатного файла настроек.
Конвертация выполняется в `dataset.download_sequence`, отдельной команды convert нет.

Для одного исследовательского запуска с provenance и SE(3)-метриками используйте
тот же файл и выберите вариант и запись:

```bash
make run-research VARIANT=orbslam3_no_loop DATASET=grandtour-alphasense SEQUENCE=kaeb_1
make evaluate
make visualize
```

`Evaluation` применяется при `make evaluate` к research run; `make run` сохраняет
протокол, но автоматически метрики не вычисляет. `make evaluate`/`make visualize`
работают с research run. Встроенные native оценка/сравнение доступны через команды
VSLAM-LAB с сохранённым native experiment YAML; их Sim(3)-протокол отличается от
исследовательского SE(3).

## Формат и источники

```text
${VIO_DATA_DIR}/VSLAM-LAB-Benchmark/<DATASET>/<sequence>/
  rgb_0/, rgb_1/
  rgb.csv
  imu_0.csv
  calibration.yaml
  groundtruth.csv
  preparation_report.json
```

GrandTour использует штатный `grandtour-alphasense`: global-shutter камеры и
BMI085. Основные записи — KÄB-1 и ALB-1. Стандартный resize `[640,480]` сохраняет
пропорции. Для наших outdoor-записей проверяется наличие GNSS/INS
`cpt7_ie_tc_odometry`; prism-only fallback не принимается как 6DoF GT.
HF revision данных штатным адаптером не закрепляется; это отмечено в provenance.

BotanicGarden использует VLIO bags и corrected `gt_<sequence>_qnew.bag` с OneDrive и
калибровку из закреплённого GitHub revision. Bags и GT проверяются по MD5.
Native gray stereo — 960×600/10 Hz; Xsens IMU — nominal 400 Hz.
Извлечение использует `header.stamp`, стереопары сопоставляются по одинаковому
времени. Corrected GT VLP16 приводится к Xsens:
`T_world_xsens = T_world_vlp16 @ inverse(T_xsens_vlp16)`.

Исходный GT сохраняется в `groundtruth_vlp16.csv`. Позы с NaN/Inf исключаются
без интерполяции; их timestamps перечислены в `reference_metadata.json`.
В реальной `1018_00` обнаружена одна такая поза. Reference использует
VIO-assisted tracking и не полностью независим от визуального метода.
Исходные bags, GT и калибровка сохраняются. Прерванный собственный импорт
BotanicGarden возобновляет hooks; неизвестные частичные каталоги не перезаписываются.

`make test` проверяет миграцию, окружение, входы runner и evaluator.
Успешная подготовка не доказывает успешность VIO. На нестабильном T7 реальные
прогоны не запускать; локальная проверка импорта выполнена на внутреннем NVMe.

## Состояние миграции

Адаптер BotanicGarden пока находится в рабочем дереве submodule. Публикация,
commit и обновление pin ещё не выполнены: чистый checkout пока его не получает.
Старый EuRoC-like exporter, manifest, storage YAML и его тесты удалены после
проверки BotanicGarden, KÄB-1 и ALB-1. `zarr`, `numcodecs`, `rosbags`, `requests`,
`scipy`, `Pillow` удалены из bootstrap requirements; подготовка использует Pixi,
а зависимости evo/viewer остаются отдельными. Уже установленные окружения и
данные не удалялись. Историческая инструкция — [здесь](docs/legacy-dataset-preparation.md).

## Оценка и просмотр результатов через evo

```bash
make evaluate RUN_DIR=/path/to/run
make visualize RUN_DIR=/path/to/run
make visualize VIS_ARGS="--evaluation-dir /path/to/run/evaluations/<date> --save /tmp/comparison.rrd"
```

Без `RUN_DIR` выбирается последний датированный запуск. Внутри него `visualize`
выбирает последнюю завершённую оценку, пропуская папки прерванного сохранения.
`evaluate` и `visualize`
используют отдельное `.venv-rerun` с закреплёнными evo 1.35.2 и Rerun 0.31.4;
окружение алгоритма VSLAM-LAB и его lockfile не меняются. Для этого окружения
Makefile очищает `PYTHONPATH`, чтобы системные ROS-пакеты не попадали в оценку. `make test` проверяет
также интеграцию оценки и headless-экспорт Rerun.

`Evaluation` в YAML эксперимента сохраняется в `run_provenance.json` при запуске.
Оценка читает этот снимок, а не текущий конфиг. Для старого запуска без снимка
или отдельного протокола используйте `EVAL_ARGS="--protocol /path/to/evaluation.yaml"`:
файл содержит только mapping полей `Evaluation`. Другой GT можно явно задать
через `EVAL_ARGS="--gt /path/to/groundtruth.csv"`.

Каждая оценка создаёт отдельный `evaluations/<date>/` с `protocol.yaml`,
`summary.json` и стандартными ZIP evo: `ape_position_m`, `ape_orientation_deg`,
`rpe_position_m`, `rpe_orientation_deg`. ZIP сохраняют статистику и ошибки;
APE ZIP также содержит сопоставленные выровненные траектории. Их можно читать
через evo и сравнивать через `evo_res`. Rerun показывает сохранённые результаты
без чтения исходных CSV и пересчёта. Повторная оценка не перезаписывает прежнюю.

Протокол: SE(3) либо отсутствие выравнивания, без scale correction;
Стандартный `evo.sync.associate_trajectories` с допуском 0.01 s: для каждой
позы траектории с меньшим числом поз выбирается ближайшая поза другой траектории.
Повторное использование поз допускается. Отчёт разделяет число пар и число
уникальных сопоставленных estimate/GT-поз; доля оценённых сохранённых поз
считается по уникальным estimate-позам. `matched_poses` сохраняется как прежнее
имя числа пар, равное `matched_pairs`.
Экстраполяция за временные границы GT запрещена.
Наносекунды читаются как int64; общий origin вычитается до перевода в секунды.
Quaternion CSV имеет порядок xyzw, evo — wxyz: это не EuRoC GT CSV.

`estimate_frame: camera` и `camera: rgb_0` задают преобразование через
`T_WB = T_WC @ inverse(T_BC)`. Перед оценкой нового алгоритма подтвердите
семантику его экспортированной позы; для body-позы задайте `estimate_frame: body`.
`evaluate_orientation: true` требует 6DoF-эталон; identity-only orientation
вызывает ошибку. Для проверенного position-only reference можно явно отключить
ориентационные метрики, согласовав физическую точку сравнения.

RPE использует пары по расстоянию GT: `rpe_delta_m: 1.0`, относительный допуск
`rpe_relative_tolerance: 0.1`, все подходящие пары. Пары не пересекают разрывы
более `max_pose_gap_s: 1.0`. Rerun показывает полные статические ломаные через
сопоставленные сохранённые позы, а длинные промежутки отмечает серыми маркерами.
Интервалы, исключённые маской качества GT, ломаная не соединяет. Этот порог —
правило сегментации сохранённых keyframes, а не детектор tracking loss.
При отсутствии подходящих пар RPE отмечается как недоступная, без фиктивных нулей.

Опциональный `gt_valid_intervals_ns: [[start_ns, end_ns], ...]` задаёт общие
интервалы качества GT. Они должны быть упорядочены и не пересекаться; границы
включены, исключённые интервалы не соединяются RPE. Маску следует выбирать по
качеству эталона, а не ошибкам метода. Без маски качество GT не сертифицируется.

Оцениваются сохранённые keyframes. `summary.json` отдельно показывает статус
запуска, число сопоставленных поз, временные разрывы и предупреждения native log.
Временной размах не выдаётся за полноту обработки изображений. Несколько карт
по native log отклоняются; parsing логов не является полной диагностикой resets.
Незавершённый запуск допускается только как явно отмеченный частичный результат.

Runner сохраняет журнал `vslamlab_exp_log.csv` в формате VSLAM-LAB; после оценки
он получает `EVALUATION=evo` и путь к артефактам. Встроенный evaluator VSLAM-LAB
с захардкоженным Sim(3) не вызывается. Его старые plot/compare-команды не являются
автоматически совместимыми с новым расположением оценок; сравнение метрик — через evo.

Rerun использует мост evo для точек, линий, residuals и графиков ошибок.
Отправка ориентаций — небольшой локальный адаптер: в evo 1.35.2 мост
переставляет quaternion по плоскому массиву вместо оси каждой позы.
Исправление представления проверяется отдельно; метрики остаются расчётом evo.
