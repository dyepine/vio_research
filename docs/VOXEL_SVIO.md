# Voxel-SVIO и сравнение трёх stereo-inertial методов

Авторская реализация: https://github.com/ZikangYuan/voxel_svio,
commit `eac6b87d0f925b96ddd5c5c6b0dcda3d36c7ab5f`.
Baseline VSLAM-LAB — `Module: voxel-svio`, режим `stereo-vi`.

```bash
make run CONFIG=configs/experiments/orbslam3_okvis1_voxel_svio.yaml JOBS=3 RGB_MAX=200
make run CONFIG=configs/experiments/orbslam3_okvis1_voxel_svio.yaml JOBS=3
make evaluate RUN_DIR=/absolute/path/to/comparison EVAL_ARGS=--saved-protocol
```

Матрица: ORB-SLAM3, OKVIS 1, Voxel-SVIO × GrandTour Alphasense `kaeb_1`
и BotanicGarden `1018_13`, по одному запуску. Все получают `rgb_0`, `rgb_1`,
`imu_0` и один и тот же проверенный интервал камер/IMU. `FrameStart` отсутствует.
Для GrandTour применяется опубликованный Allan-профиль из конфига OKVIS 1;
для BotanicGarden — рабочий профиль авторов ORB-SLAM3. Плотности и random walk
одинаковы для трёх методов и записываются в per-run `calibration_exp.yaml`.
Профиль BotanicGarden не объявляется измеренным шумом датчика.

Loop closure выключен у ORB-SLAM3; OKVIS 1 и Voxel-SVIO работают как VIO,
без place-recognition/loop-closure backend. Калибровка фиксирована.
Нативные параметры оценивателей различаются; используемые настройки сохраняются.
Оценка через штатный evo: `align: origin`, `correct_scale: false`, ассоциация
с GT с допуском 0.05 s, RPE на 1 м с relative tolerance 0.1.
Сохранённые позы не интерполируются. Неинициализированные/неполные/упавшие
запуски нужно учитывать вместе с ошибками, а не исключать из сравнения.

`JOBS=3` запускает отдельный процесс на каждый вариант метода. Две записи
одного метода идут последовательно. CSV и временные файлы разных работников
не пересекаются; время начала/конца и PID записываются в
`inputs/workers/*.execution.json`. Главный `experiment.yaml` остаётся единой
точкой оценки всех шести запусков. На Linux стандартный `forkserver`
предзагружает VSLAM-LAB один раз, воркеры разделяют неизменяемые страницы памяти;
подготовка выполняется в короткоживущем процессе, координатор не держит лишнюю
копию framework. На платформах без `forkserver` применяется `spawn`.
Выбранный способ записывается в `execution.json`.
При параллельном исполнении методы делят
CPU/RAM, поэтому измеренные wall time не являются сравнением быстродействия
изолированных алгоритмов. Защита VSLAM-LAB по RAM остаётся активной;
не запускайте параллельно с матрицей тяжёлые сборки и regression-тесты.

## Нативная интеграция

Оцениватель компилируется из оригинальных `src/*.cpp`. Файловая обвязка
заменяет ROS-подписки, parameter server и публикацию визуализации.
MSCKF, инициализаторы, tracking, triangulation, state update и voxel map
остаются авторскими. Реальные PCL-контейнеры сохраняются: используются
заголовки Ubuntu `libpcl-dev` 1.12.1, распакованные локально с проверкой SHA256.
Пакеты в систему не устанавливаются, ROS master и replay не нужны.
Исходники загружаются через partial/sparse clone без 26 MB demo GIF.

Два patch доступны в `Baselines/extra-files/voxel_svio/`:

- `offline.patch`: ROS-входы/выходы заменены файловыми; `gravity_mag` из
  калибровки передаётся и initializer, и propagator. В upstream propagator
  иначе остаётся на hard-coded default 9.81 при другом настроенном g.
- `compatibility.patch`: `addPointToVoxel` возвращает `false`, когда
  существующий voxel заполнен. В upstream в этой ветке отсутствует return,
  хотя вызывающий код использует bool; это undefined behavior.

За основу настроек взят авторский `config/euroc.yaml`. Для offline-запуска
бюджет dynamic-initialization MLE увеличен с 0.05 до 5 s, число потоков — 2.
Камеры и IMU заменяются калибровкой выбранной записи. Остальные настройки
взяты из рецепта; это не подбор параметров по результатам текущего сравнения.

Timestamp для расчётов — секунды относительно сохранённого int64 origin;
в CSV экспорта возвращается исходный int64 ns конкретного обработанного кадра.
Экспорт происходит только после нативного feature/state update.
Положение IMU и JPL rotation `R_GtoI` преобразуются в Hamilton-позу `T_WI`,
затем в корпус: `T_WB = T_WI * inverse(T_BI)`.
Камерная калибровка передаётся как `T_IC = inverse(T_BI) * T_BC`.
Поддерживаются `equid4`, `radtan4` и pinhole; остальные модели отвергаются.
Параметры времени/калибровки не оптимизируются в этом сравнении.

Итоги каждого запуска включают `voxel_svio_native.yaml`,
`voxel_svio_images.tsv`, `voxel_svio_provenance.json`, исходный native `pose.txt`,
стандартный `system_output_00000.txt` и `00000_KeyFrameTrajectory.csv`.
Нативный `pose.txt` сохраняет авторский формат и относительное время;
для оценки используется только стандартный CSV с преобразованной позой корпуса.

Сборка использует toolchain Ubuntu 22.04: GCC 11, CMake, Eigen 3.4,
OpenCV 4.5.4, Ceres 2.0, Boost 1.74 и yaml-cpp 0.7.

```bash
bash external/VSLAM-LAB/Baselines/extra-files/voxel_svio/build.sh
env -u LD_LIBRARY_PATH ctest --test-dir external/VSLAM-LAB/Baselines/Voxel-SVIO/build --output-on-failure
```

Системный `LD_LIBRARY_PATH` очищается только для сборки и дочернего бинарника.
Нативный тест проверяет заполнение voxel и JPL/Hamilton ориентацию;
Python-тесты проверяют калибровку, плотности шума и преобразование IMU/body.
Общие проверки представления stereo-входов вынесены в `stereo_vi_inputs.py`
и используются также OKVIS 1. Изменения интеграции пока локальные в submodule,
они ещё не входят в закреплённый fork commit.

## Проверенный полный прогон

Артефакты: `results/vio/VSLAM-LAB-Evaluation/comparison_20261015T225857_6630a379/`.
В каталоге находятся `report.md`, `comparison.csv`, `coverage.json`, PNG/PDF,
сохранённые входы, pin/hash исходников и нативные журналы всех шести запусков.

Полные записи GrandTour Alphasense `kaeb_1` (4788 пар) и BotanicGarden `1018_13` (1600 пар), один запуск на метод/запись. Все шесть запусков завершены и оценены.

Stereo-inertial, loop closure выключен, одинаковые входные интервалы и IMU noise profiles. evo: origin alignment, без коррекции масштаба, ассоциация ±0.05 s, RPE на 1 м (relative tolerance 0.1). Оценка на сохранённых позах; ORB сохраняет ключевые кадры. GT не сертифицирован как безошибочный.

| Запись | Метод | APE RMSE, м | RPE 1 м RMSE, м | APE ориентации, ° | Позы / совпадения | Интервал, % | Старт, с | Макс. разрыв, с |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| grandtour-alphasense/kaeb_1 | orbslam3 | 6.1456 | 0.9224 | 4.364 | 801 / 801 | 98.31 | 7.600 | 3.000 |
| botanicgarden/1018_13 | orbslam3 | 1.3302 | 0.0608 | 1.151 | 498 / 495 | 98.75 | 1.700 | 1.300 |
| grandtour-alphasense/kaeb_1 | okvis1 | 2.4101 | 0.0508 | 3.674 | 4788 / 4788 | 100.00 | 0.000 | 0.200 |
| botanicgarden/1018_13 | okvis1 | 1.9247 | 0.0921 | 1.421 | 1599 / 1585 | 100.00 | 0.000 | 0.200 |
| grandtour-alphasense/kaeb_1 | voxel-svio | 2.1737 | 0.0414 | 2.986 | 4708 / 4708 | 98.33 | 8.000 | 0.200 |
| botanicgarden/1018_13 | voxel-svio | 1.1470 | 0.0613 | 1.110 | 1577 / 1564 | 98.56 | 2.300 | 0.100 |

Интервал — длительность от первой до последней сохранённой позы / длительность входа; внутренние разрывы показаны отдельно. Разные моменты инициализации и частота экспорта ограничивают прямое сравнение метрик. Это один trial, без статистики повторов; wall time при совместном CPU/RAM не является тестом быстродействия.

Все три работника стартовали с разбросом 0.018 s, общий период работы 390.4 s. Наблюдаемый пик RAM при замерах каждые 5 s: 93.0%; стандартный порог 95% сохранён.

У ORB-SLAM3 на GrandTour три сообщения `Fail to track local map!`; сброса/создания второй карты не было. Проверяйте разрывы и покрытие вместе с APE. Начальный участок до инициализации Voxel-SVIO отсутствует в экспорте.

Ранний spawn-прогон `comparison_20261015T224919_ac54361d` остановился по лимиту RAM; его частичные результаты не включены. Текущий прогон использует forkserver с общими страницами framework. Никакие пользовательские приложения не закрывались, RAM guard не ослаблялся.

Данные: [comparison.csv](../results/vio/VSLAM-LAB-Evaluation/comparison_20261015T225857_6630a379/comparison.csv), [coverage.json](../results/vio/VSLAM-LAB-Evaluation/comparison_20261015T225857_6630a379/coverage.json), [execution evidence](../results/vio/VSLAM-LAB-Evaluation/comparison_20261015T225857_6630a379/validation/execution_summary.json), [source manifest](../results/vio/VSLAM-LAB-Evaluation/comparison_20261015T225857_6630a379/inputs/source_manifest.json), [source audit](../results/vio/VSLAM-LAB-Evaluation/comparison_20261015T225857_6630a379/validation/upstream_core_audit.json).

Графики используют все сохранённые позы без интерполяции: [GrandTour](../results/vio/VSLAM-LAB-Evaluation/comparison_20261015T225857_6630a379/figures/grandtour-alphasense_kaeb_1_errors.png), [BotanicGarden](../results/vio/VSLAM-LAB-Evaluation/comparison_20261015T225857_6630a379/figures/botanicgarden_1018_13_errors.png). Карты APE и PDF находятся рядом.

Проверки: 34 migration-теста, 18 evaluation-тестов, 3 Voxel Python-теста,
7 stereo regression-тестов (OKVIS/DROID), 1 нативный CTest — прошли.
`git diff --check` в корне и submodule, `bash -n` build-рецептов — без ошибок.
Аудит upstream: 18 остальных вычислительных translation units неизменны;
9 основных функций `stereoVio.cpp`, включая `run`, initialization и state update,
совпадают с pinned upstream. Evidence — `validation/upstream_core_audit.json`.
Известный отдельный сбой core bootstrap-теста на ранее изменённом
`dataset_grandtour.py` сохраняется: текущая рабочая копия расходится с pinned fork.
Полный clean-checkout bootstrap для новых локальных adapters пока не подтверждён.
