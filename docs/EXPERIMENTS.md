# Дополнительные и исторические эксперименты

Основная матрица сдачи — `configs/experiments/report.yaml`.
Остальные конфиги сохранены по прежним путям: на них ссылаются тесты,
документация и сохранённые provenance. Их наличие не расширяет основной benchmark.

| Назначение | Конфиги в `configs/experiments/` |
| --- | --- |
| Три основных метода на GrandTour/BotanicGarden | `orbslam3_okvis1_voxel_svio.yaml` |
| Те же методы на GEODE rectified | `geode_orbslam3_okvis1_voxel_svio.yaml` |
| GEODE: исходные изображения и модели дисторсии | `geode_raw_radtan4_orbslam3_okvis1_voxel_svio.yaml`, `geode_raw_radtan5_orbslam3_okvis1.yaml` |
| Контроль ректификации Voxel-SVIO | `geode_voxel_svio_radtan4_vs_rectified.yaml` |
| sqrtVINS, дополнительно упомянутый в отчёте | `geode_sqrtvins.yaml`, `kaeb1_sqrtvins_voxel_svio_control.yaml`, `geode_offroad7_sqrtvins_voxel_svio.yaml` |
| A/B random walk, только ORB-SLAM3 | `orbslam3_random_walk_ab.yaml` |
| SchurVINS, отдельное исследование | `geode_schurvins.yaml`, `ros1_schurvins.yaml` |
| Раннее сравнение ORB mono/stereo с OKVIS2 | `comparison.yaml`, `orbslam3_okvis2_no_loop.yaml` |
| Отдельный baseline OKVIS1 | `okvis1_stereo_vi.yaml` |
| GPU-эксперимент PyCuVSLAM | `orbslam3_pycuvslam_stereo_vi.yaml` |
| Stereo DROID-SLAM без IMU | `droidslam_stereo.yaml` |

Для каждого выбранного эксперимента:

```bash
make prepare CONFIG=configs/experiments/<name>.yaml
make run CONFIG=configs/experiments/<name>.yaml JOBS=1
make evaluate RUN_DIR=/absolute/path/to/new/comparison EVAL_ARGS=--saved-protocol
```

`--saved-protocol` воспроизводит именно протокол запуска. Для переоценки старой
матрицы по текущему конфигу нужно передать `CONFIG=...` без `--saved-protocol`.
В частности, опорная матрица GrandTour/BotanicGarden запускалась с `origin`,
а таблица отчёта использует её последующую оценку с `SE3`.

`configs/datasets/selected.yaml` — единственный dataset-only выбор: три записи
основного отчёта. Он используется при `make prepare` без `CONFIG` на новом checkout.
Для подготовки отдельного варианта GEODE передавайте соответствующий experiment YAML;
`make prepare CONFIG=...` читает только его `Datasets`, методы при этом не запускаются.

sqrtVINS включён как дополнительная проверка; это не четвёртая строка основной
таблицы. Её источники не подтверждают автоматически все результаты sqrtVINS.
SchurVINS, PyCuVSLAM, DROID-SLAM и FoMo не входят в выводы основной таблицы.
Собственные адаптеры, короткие проверки и диагностические варианты не следует
выдавать за независимую валидацию полной upstream-системы.
