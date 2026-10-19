# VIO research

Сравнение stereo-inertial одометрии **OKVIS 1, ORB-SLAM3 и Voxel-SVIO**
на outdoor-записях наземных роботов: BotanicGarden `1018_13`,
ANYmal GrandTour `kaeb_1` и GEODE Offroad1 γ.
Замыкание петель отключено. Подготовка, запуск и оценка используют
закреплённый fork VSLAM-LAB и Pixi; APE/RPE вычисляет стандартный evo.

## Запуск через Docker Compose

На хосте нужны **Git и Docker с Compose**. CMake, компилятор, OpenCV,
Ceres и остальные C++ зависимости устанавливаются автоматически при сборке
образа Ubuntu 22.04 x86_64. Pixi и Python-окружения устанавливает bootstrap
внутри контейнера; системный ROS и ручной `apt install` на хосте не нужны.

```bash
git clone --branch integration/feature-history --recurse-submodules https://github.com/dyepine/vio_research.git
cd vio_research
docker compose build
docker compose run --rm vio make prepare
docker compose run --rm vio make run JOBS=1
docker compose run --rm vio make evaluate \
  RUN_DIR=/results/VSLAM-LAB-Evaluation/comparison_YYYYMMDDTHHMMSS_HASH EVAL_ARGS=--saved-protocol
```

`RUN_DIR` — путь, напечатанный runner **внутри контейнера**. Данные сохраняются
на хосте в `datasets/`, результаты — в `results/vio/`. Для уже скачанных данных
на другом диске перед командами задайте:

```bash
export VIO_DOCKER_DATA_DIR=/path/to/existing/vio_research/data
# Необязательно: другое место для результатов.
export VIO_DOCKER_RESULTS_DIR=/path/to/results
```

Контейнер использует отдельные volumes для Pixi, кэшей и нативных сборок;
существующие окружения и бинарники хоста не переиспользуются. Исходники входят в образ; после изменения кода повторите `docker compose build`.
Git metadata монтируется для чтения, чтобы bootstrap проверял закреплённый submodule. Результаты создаются с UID/GID владельца checkout, а локальная `.envrc`
хоста в контейнере не исполняется. Конфигурация контейнера — `scripts/env.sh`,
машинные пути задаются переменными образа и bind mounts в `compose.yaml`.
Dockerfile, entrypoint и правила build context лежат в `docker/`.

```bash
docker compose run --rm vio make test
docker compose run --rm vio make run RGB_MAX=200       # короткая проверка
docker compose run --rm vio make run PLAN=1            # материализация без VIO
docker compose run --rm vio make run CONFIG=configs/experiments/sqrtvins.yaml
docker compose run --rm vio python3 scripts/build_report_table.py --check  # без датасетов
```

`PLAN=1` требует подготовленные данные. Короткая проверка не является полным
benchmark. Новая матрица и каждая версия оценки сохраняются отдельно.
Для первого скачивания нужны сеть и место; подготовка проверяет бюджет 125 GB
и запас 15 GB. При `JOBS>1` методы делят CPU/RAM, поэтому их wall time
не характеризует изолированное быстродействие.

### Локальный Pixi workflow

Для уже настроенной Ubuntu 22.04 остаются `make prepare`, `make run`,
`make evaluate` и `make test`. Нативные сборки требуют пакеты, перечисленные
в `docker/Dockerfile`; для запуска без их ручной установки используйте Compose выше.
OKVIS1 требует Ceres 2.0, Ceres 2.2+ не поддерживается.
Bootstrap устанавливает локальный Pixi 0.81.0 с SHA-256 и окружения из
`external/VSLAM-LAB/pixi.lock`. Данные по умолчанию — `$HOME/datasets/vio_research`.
`.envrc` создаётся через `make configure` и автоматически не перезаписывается.

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
Подробнее — [GEODE](docs/DATASETS.md#geode) и [источники таблицы](artifacts/report/README.md).

Авторский текст отчёта и итоговый PDF остаются отдельной работой автора.

Результаты проверок и оставшиеся ограничения — [VALIDATION.md](docs/VALIDATION.md).

## Устройство репозитория

- `configs/experiments/report.yaml` — основная матрица 3 × 3 с общими профилями IMU.
- `configs/experiments/sqrtvins.yaml` — дополнительный метод из отчёта на тех же записях.
- `scripts/` — подготовка, материализация экспериментов и вызовы штатного evaluator.
- `external/VSLAM-LAB` — submodule с адаптерами датасетов, методов и модулем `Evaluate`.
- `tests/` — проверки подготовки, калибровки, запуска и стандартных метрик evo.
- [Датасеты и системы координат](docs/DATASETS.md).
- [Методы и адаптеры](docs/METHODS.md), включая дополнительный sqrtVINS.

Точную ревизию fork задаёт gitlink `external/VSLAM-LAB`, а не имя ветки в `.gitmodules`.
Bootstrap сохраняет checkout и останавливается при несовпадении ревизии.
При публикации изменений сначала должны быть доступны коммиты fork, затем
основного репозитория. Исторические конфиги и документы доступны в Git; ссылки на ревизии —
в [VALIDATION.md](docs/VALIDATION.md#исторические-материалы).
