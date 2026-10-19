# VIO research

Сравнение stereo-inertial одометрии **OKVIS 1, ORB-SLAM3 и Voxel-SVIO**
на outdoor-записях наземных роботов: BotanicGarden `1018_13`,
ANYmal GrandTour `kaeb_1` и GEODE Offroad1 γ.
Замыкание петель отключено. Подготовка, запуск и оценка используют
закреплённый fork VSLAM-LAB и Pixi; APE/RPE вычисляет стандартный evo.

## Воспроизведение

Поддерживаемое окружение нативных адаптеров — **Ubuntu 22.04 x86_64**.
Помимо `git`, `make`, `curl`, `tar`, `sha256sum` и `dpkg-deb`, для сборки нужны
системные dev-пакеты. На чистой Ubuntu их устанавливают один раз:

```bash
sudo apt-get update
sudo apt-get install -y git make curl ca-certificates tar dpkg-dev \
  build-essential cmake libopencv-dev libeigen3-dev libceres-dev \
  libgoogle-glog-dev libsuitesparse-dev libboost-filesystem-dev \
  libboost-system-dev libboost-thread-dev libboost-date-time-dev libyaml-cpp-dev
```

Нативные сборки используют Ceres 2.0 из Ubuntu 22.04; Ceres 2.2+ для OKVIS1
не поддерживается. Системный ROS не нужен. Это Pixi workflow с явно указанными
системными зависимостями, а не полностью изолированная сборка всех C++ библиотек.

```bash
git clone --branch integration/feature-history --recurse-submodules https://github.com/dyepine/vio_research.git
cd vio_research
# При checkout другой ветки повторить: git submodule update --init
make prepare CONFIG=configs/experiments/report.yaml
make run CONFIG=configs/experiments/report.yaml JOBS=1
make evaluate CONFIG=configs/experiments/report.yaml \
  RUN_DIR=/absolute/path/to/new/comparison EVAL_ARGS=--saved-protocol
```

`RUN_DIR` — каталог `comparison_...`, напечатанный runner. Каждая новая матрица
и версия оценки сохраняются отдельно. Первый `make prepare` устанавливает локальный
Pixi 0.81.0 с SHA-256 и среды из `external/VSLAM-LAB/pixi.lock`, затем скачивает
и подготавливает только три записи эксперимента. Нужны сеть и достаточно места;
перед подготовкой проверяются бюджет 125 GB и запас 15 GB.

Данные по умолчанию находятся в `$HOME/datasets/vio_research`, результаты —
в `results/vio/`. Для другого диска задайте `VIO_DATA_DIR` при каждой команде
или сохраните путь в `.envrc`, созданной `make configure`.
`.envrc` исполняется как shell-код и автоматически не перезаписывается.
Приведённые команды явно задают `CONFIG`, поэтому подходят и для старой `.envrc`.
На новом checkout defaults из `scripts/env.sh` также выбирают `report.yaml`.

```bash
make run CONFIG=configs/experiments/report.yaml PLAN=1       # материализация без VIO
make run CONFIG=configs/experiments/report.yaml RGB_MAX=200  # короткая проверка
make test                                                 # offline-тесты в Pixi
python3 scripts/build_report_table.py --check               # проверка сохранённой таблицы
```

`PLAN=1` требует подготовленные данные. Проверка на 200 кадрах не является полным
benchmark. `JOBS=1` запускает методы последовательно; при параллельном запуске
они делят RAM/CPU, а wall time не характеризует изолированное быстродействие.

## Результаты отчёта

Сохранённые числа, LaTeX-таблица, графики, стандартные ZIP evo и источники —
в [artifacts/report](artifacts/report/README.md). Они доступны без скачивания датасетов.
Это опорные исторические прогоны, а не обещание побайтового совпадения нового запуска.
Новый общий конфиг использует текущие исправления адаптеров, включая memory fix
Voxel-SVIO; исторические артефакты сохраняют исходные хеши и предупреждения.

Протокол: **SE3 без подгонки масштаба**, association evo с допуском 0.05 s,
RPE на 1 м пути GT с относительным допуском 0.1, `all_pairs=True`.
Разрывы поз более 1 s разделяют RPE-сегменты. Оценивается body-поза;
камерный экспорт ORB-SLAM3 преобразуется через калибровку.
APE/RPE позиции указаны в метрах, ориентации — в градусах; сводная таблица содержит RMSE.
Методы сохраняют разные timestamps, ORB-SLAM3 — ключевые кадры.

GEODE требует отдельной оговорки: используется принятая поправка ориентации GT,
а качество GNSS/INS и внешней калибровки независимо не подтверждено.
`×` для Voxel-SVIO означает, что устойчивое прохождение не подтверждено по истории
попыток; исходные численные метрики опорной попытки сохранены.
Подробнее — [GEODE](docs/GEODE.md) и [источники таблицы](artifacts/report/README.md).

Авторский текст отчёта и итоговый PDF остаются отдельной работой автора.

Результаты проверок и оставшиеся ограничения — [VALIDATION.md](docs/VALIDATION.md).

## Устройство репозитория

- `configs/experiments/report.yaml` — основная матрица 3 × 3 с общими профилями IMU.
- `scripts/` — подготовка, материализация экспериментов и вызовы штатного evaluator.
- `external/VSLAM-LAB` — submodule с адаптерами датасетов, методов и модулем `Evaluate`.
- `tests/` — проверки подготовки, калибровки, запуска и стандартных метрик evo.
- [Дополнительные эксперименты](docs/EXPERIMENTS.md) — sqrtVINS и остальные варианты.
- Документация интеграций: [OKVIS1](docs/OKVIS1.md), [Voxel-SVIO](docs/VOXEL_SVIO.md),
  [sqrtVINS](docs/SQRTVINS.md), [SchurVINS](docs/SCHURVINS.md).

Точную ревизию fork задаёт gitlink `external/VSLAM-LAB`, а не имя ветки в `.gitmodules`.
Bootstrap сохраняет checkout и останавливается при несовпадении ревизии.
При публикации изменений сначала должны быть доступны коммиты fork, затем
основного репозитория. Исследовательские конфиги и исторические результаты
сохраняются отдельно от основного сценария; прежняя подробная инструкция —
[legacy-workflow.md](docs/legacy-workflow.md).
