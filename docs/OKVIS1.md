# OKVIS 1 stereo-inertial в VSLAM-LAB

Метод каталога: `Module: okvis1`, `Parameters.mode: stereo-vi`.
Реализация оценивателя — [авторский OKVIS 1.1.3, ветка fix/modernise](https://github.com/ethz-asl/okvis/tree/33ac70b4d95df98cd662086dc897b90a6f35d5a9),
revision `33ac70b4d95df98cd662086dc897b90a6f35d5a9`.
Свой код отвечает за входы VSLAM-LAB и экспорт; алгоритм OKVIS не переписан.

```bash
make run CONFIG=configs/experiments/okvis1_stereo_vi.yaml RGB_MAX=200
make evaluate RUN_DIR=/path/to/new/comparison EVAL_ARGS=--saved-protocol
```

Конфиг запускает GrandTour Alphasense `kaeb_1` и BotanicGarden `1018_13`.
Для BotanicGarden не задаётся `FrameStart`: запись запускается с начала
доступного интервала камер/IMU, без поправки на пересвет.
Без `RGB_MAX` запускаются полные записи. Настройки шума совпадают с
`orbslam3_okvis2_no_loop.yaml`; priors/limits заданы отдельно через
`imu_overrides`. Оценка: `align: origin`, `correct_scale: false`.
Это отдельный исторический эксперимент. Основная матрица сдачи —
`report.yaml` с SE3; её результаты описаны в [artifacts/report](../artifacts/report/README.md).
Интеграция включена в закреплённый локальный коммит submodule VSLAM-LAB.
Новые коммиты fork ещё не опубликованы; для клонирования на другой машине
сначала требуется их публикация. Системные зависимости сборки остаются внешними.

При первом запуске baseline собирается автоматически в `Baselines/OKVIS1/build`.
Сборка использует системный toolchain Ubuntu 22.04: GCC 11, CMake 3.22,
OpenCV 4.5.4, Eigen 3.4, Ceres 2.0, Boost 1.74, glog и SuiteSparse.
Системные пакеты автоматически не устанавливаются. Нужны dev-пакеты
`build-essential cmake libopencv-dev libeigen3-dev libceres-dev
libgoogle-glog-dev libsuitesparse-dev libboost-filesystem-dev` и `git`.
BRISK и OpenGV собираются локально через upstream CMake.
BRISK фиксируется SHA256; OpenGV берётся архивом commit upstream-рецепта
с проверкой SHA256, без загрузки всей истории Git.
Patch в `Baselines/extra-files/okvis1/modernise.patch` адаптирует CMake к
Ceres 2.0 и C++14. API Ceres 2.2+ здесь не поддерживается.

Чтобы пересобрать после изменения адаптера:

```bash
bash external/VSLAM-LAB/Baselines/extra-files/okvis1/build.sh
```

Исполнение Python идёт из среды VSLAM-LAB; C++ бинарник использует системные
библиотеки. `LD_LIBRARY_PATH` очищается только у дочернего процесса OKVIS,
чтобы библиотеки Pixi/ROS не подменяли системные OpenCV/Ceres.

Адаптер читает `rgb_exp.csv`, обе камеры и `imu_0.csv`, сохраняет int64 ns,
проверяет синхронизацию и подаёт IMU с запасом 30 ms относительно камер
(OKVIS требует 20 ms). Сохраняются реальные позы оптимизированных кадров,
без IMU-пропагации и интерполяции. Перед выходом ожидается последняя оптимизация.
`T_SC = inverse(T_BI) * T_BC`; выход `T_WS` переводится в `T_WB`.
Ректификация не требуется: используются родные `equid4`, `radtan4`, `radtan8`
или pinhole. Другие модели отвергаются, коэффициенты не отбрасываются.
`imageDelay` должен быть нулём; временные метки должны быть уже откалиброваны.

В папке каждого запуска дополнительно сохраняются `okvis1_native.yaml`,
`okvis1_images.tsv`, `okvis1_provenance.json`, `okvis1_tracking.json`
и штатный `system_output_00000.txt`.
Траектория публикуется как `00000_KeyFrameTrajectory.csv` только после
успешного завершения процесса и проверки чисел и порядка временных меток.
Отсутствие визуальной инициализации (`Initialized!` из pinned `Frontend.cpp`)
считается ошибкой, даже если библиотека экспортировала позы.
Количество сообщений `Tracking failure` сохраняется в диагностике отдельно:
успешное завершение процесса само по себе не гарантирует устойчивый трекинг.
`strtod` читает субнормальные значения IMU BotanicGarden без исключения
`std::stod` при `ERANGE`; исходный CSV сохраняется.

## Проверенный запуск

Исторический полный прогон на `kaeb_1` и `1018_00` со стартом 20
(до переключения дефолтной записи на `1018_13`):
`results/vio/VSLAM-LAB-Evaluation/comparison_20261015T215055_51ec2301/`.
Оба native запуска завершились с `STATUS=completed`, `SUCCESS=True`;
визуальная инициализация прошла, сообщений `Tracking failure` нет.

| Запись | Поданные пары | Сохранённые позы | Пары с GT | APE RMSE, м | RPE RMSE на 1 м, м |
|---|---:|---:|---:|---:|---:|
| GrandTour Alphasense kaeb_1 | 4788 | 4787 | 4787 | 2.4913 | 0.04498 |
| BotanicGarden 1018_00, старт 20 | 944 | 944 | 935 | 1.5592 | 0.07452 |

Протокол — `origin`, без коррекции масштаба, допуск ассоциации 0.05 s.
Это по одному запуску; таблица не устанавливает превосходство над другими методами.
В GrandTour внутренний `FrameSynchronizer` OKVIS отбросил один ранний кадр
(индекс 1 в `rgb_exp.csv`); недостающая поза не восстанавливалась интерполяцией.
Подробные evo-артефакты и PNG/PDF лежат в `evaluations/00000/` каждой записи;
общая таблица — `comparison.csv` в корне прогона.

Проверки: 5 тестов адаптера, 33 migration и 18 evaluation — passed;
повторная сборка и `git diff --check` — passed. В общем наборе tests остаётся
изначальное падение `test_clean_checkout_and_second_invocation_deliver_same_adapter`:
незакоммиченный `dataset_grandtour.py` отличается от версии чистого checkout.
Остальные 28 тестов того общего запуска прошли (тогда в нём было 4 теста OKVIS).
Логи проверок сохранены в `results/vio/okvis1_integration_validation/`.
Повторная проверка BotanicGarden со старта 0 корректно вернула ошибку:
`initialized=false`, 199 предупреждений о трекинге, финальный CSV не опубликован
(`results/vio/okvis1_uninitialized_check/`).
