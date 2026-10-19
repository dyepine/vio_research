# Эксперименты отчёта

В `configs/experiments/` оставлены два файла:

| Конфиг | Содержание |
| --- | --- |
| `report.yaml` | OKVIS1, ORB-SLAM3, Voxel-SVIO × GrandTour `kaeb_1`, BotanicGarden `1018_13`, GEODE `offroad1` |
| `sqrtvins.yaml` | Дополнительный sqrtVINS на тех же трёх записях, с теми же профилями IMU и протоколом |

Основной запуск:

```bash
make prepare
make run
make evaluate RUN_DIR=/absolute/path/to/new/comparison EVAL_ARGS=--saved-protocol
```

Дополнительный метод:

```bash
make prepare CONFIG=configs/experiments/sqrtvins.yaml
make run CONFIG=configs/experiments/sqrtvins.yaml JOBS=1
make evaluate RUN_DIR=/absolute/path/to/new/comparison EVAL_ARGS=--saved-protocol
```

У sqrtVINS задано окно инициализации 2 s, как в успешном контроле GrandTour
и прежнем GEODE-конфиге. Новый запуск на BotanicGarden ещё не проверен;
наличие конфига не подтверждает результаты на этой записи. Источники сохранённых
контролей — [SQRTVINS.md](SQRTVINS.md).

`configs/datasets/selected.yaml` — единственный dataset-only выбор, совпадающий
с `Datasets` обеих матриц. `make prepare CONFIG=...` читает только выбор датасетов
из эксперимента и не запускает методы. Явные переменные в локальной `.envrc`
по-прежнему могут переопределять defaults.

## Исторические проверки

Из рабочего набора удалены 16 конфигов: подмножества основной матрицы,
ранние ORB/OKVIS2-сравнения, GPU-baselines и диагностические A/B. Их точные
версии остаются в Git на коммите `57913a2`; копии конфигов опорных прогонов
дополнительно сохранены в `artifacts/report/inputs/`.

| Назначение | Исторические имена |
| --- | --- |
| Подмножества основной матрицы | `orbslam3_okvis1_voxel_svio.yaml`, `geode_orbslam3_okvis1_voxel_svio.yaml`, `okvis1_stereo_vi.yaml` |
| Исходная геометрия GEODE | `geode_raw_radtan4_orbslam3_okvis1_voxel_svio.yaml`, `geode_raw_radtan5_orbslam3_okvis1.yaml` |
| Контроль ректификации | `geode_voxel_svio_radtan4_vs_rectified.yaml` |
| Частные sqrtVINS-контроли | `geode_sqrtvins.yaml`, `kaeb1_sqrtvins_voxel_svio_control.yaml`, `geode_offroad7_sqrtvins_voxel_svio.yaml` |
| A/B random walk ORB-SLAM3 | `orbslam3_random_walk_ab.yaml` |
| SchurVINS | `geode_schurvins.yaml`, `ros1_schurvins.yaml` |
| ORB/OKVIS2 | `comparison.yaml`, `orbslam3_okvis2_no_loop.yaml` |
| GPU-baselines | `orbslam3_pycuvslam_stereo_vi.yaml`, `droidslam_stereo.yaml` |

Для повторения отдельной исторической проверки восстановите конфиг вне
рабочего каталога конфигураций. Например:

```bash
git show 57913a2:configs/experiments/geode_schurvins.yaml > /tmp/geode_schurvins.yaml
make prepare CONFIG=/tmp/geode_schurvins.yaml
make run CONFIG=/tmp/geode_schurvins.yaml JOBS=1
```

Адаптеры и их тесты сохранены; удалён только набор готовых частных сценариев.
Исторический конфиг не восстанавливает автоматически прежний бинарник:
его ревизию, патчи и подготовку данных нужно сверять с provenance запуска.

`--saved-protocol` воспроизводит протокол запуска. Для переоценки старой матрицы
по текущему конфигу передавайте `CONFIG=...` без `--saved-protocol`.
Опорная матрица GrandTour/BotanicGarden запускалась с `origin`, а таблица отчёта
использует её последующую оценку с `SE3`. Источники таблицы сохраняются независимо
от очистки конфигов.
