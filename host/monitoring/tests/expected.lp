service_health,host=ryzen,observer=ryzen,service=os age_seconds=0i,impact_code=0i,reason="c_free:free_gib=64",source_timestamp=1789511726i,state_code=0i <TS>
service_check,check=c_free,check_type=disk_free,host=ryzen,observer=ryzen,service=os age_seconds=0i,code=0i,reason="free_gib=64",source_timestamp=1789511726i <TS>
service_health,host=ryzen,observer=ryzen,service=lan impact_code=0i,reason="declared:no_probe_declared;observer_shares_this_path",state_code=3i <TS>
service_check,check=declared,check_type=none,host=ryzen,observer=ryzen,service=lan code=3i,reason="no_probe_declared;observer_shares_this_path" <TS>
service_health,host=ryzen,observer=ryzen,service=docker impact_code=0i,reason="inferred_from_containers:derived:any_dependent_healthy",state_code=3i <TS>
service_check,check=inferred_from_containers,check_type=derived,host=ryzen,observer=ryzen,service=docker code=3i,reason="derived:any_dependent_healthy" <TS>
service_health,host=ryzen,observer=ryzen,service=influxdb age_seconds=0i,impact_code=0i,reason="health:http_200",source_timestamp=1789511726i,state_code=0i <TS>
service_check,check=health,check_type=http,host=ryzen,observer=ryzen,service=influxdb age_seconds=0i,code=0i,reason="http_200",source_timestamp=1789511726i <TS>
service_check,check=health_from_evaluator,check_type=http,host=ryzen,observer=ryzen,service=influxdb code=3i,reason="delegated:household-evaluator" <TS>
service_check,check=container,check_type=docker_container,host=ryzen,observer=ryzen,service=influxdb code=3i,reason="docker input omitted (D11)" <TS>
service_health,host=ryzen,observer=ryzen,service=grafana age_seconds=0i,impact_code=0i,reason="health:http_200",source_timestamp=1789511726i,state_code=0i <TS>
service_check,check=health,check_type=http,host=ryzen,observer=ryzen,service=grafana age_seconds=0i,code=0i,reason="http_200",source_timestamp=1789511726i <TS>
service_check,check=container,check_type=docker_container,host=ryzen,observer=ryzen,service=grafana code=3i,reason="docker input omitted (D11)" <TS>
service_health,host=ryzen,observer=ryzen,service=mosquitto age_seconds=0i,impact_code=0i,reason="listener:connected",source_timestamp=1789511726i,state_code=0i <TS>
service_check,check=listener,check_type=tcp,host=ryzen,observer=ryzen,service=mosquitto age_seconds=0i,code=0i,reason="connected",source_timestamp=1789511726i <TS>
service_check,check=container,check_type=docker_container,host=ryzen,observer=ryzen,service=mosquitto code=3i,reason="docker input omitted (D11)" <TS>
service_health,host=ryzen,observer=ryzen,service=iot-telegraf impact_code=0i,reason="container:docker input omitted (D11)",state_code=3i <TS>
service_check,check=container,check_type=docker_container,host=ryzen,observer=ryzen,service=iot-telegraf code=3i,reason="docker input omitted (D11)" <TS>
service_health,host=ryzen,observer=ryzen,service=iot-recovery age_seconds=3600i,impact_code=0i,reason="ok",source_timestamp=1789508126i,state_code=0i <TS>
service_check,check=task,check_type=scheduled_task,host=ryzen,observer=ryzen,service=iot-recovery age_seconds=3600i,code=0i,reason="ok",source_timestamp=1789508126i <TS>
service_check,check=fixture_file,check_type=file_mtime,host=ryzen,observer=ryzen,service=iot-recovery age_seconds=30i,code=0i,reason="ok",source_timestamp=1789511696i <TS>
service_health,host=ryzen,observer=ryzen,service=grafana-recovery age_seconds=100000i,impact_code=0i,reason="task:overdue",source_timestamp=1789411726i,state_code=2i <TS>
service_check,check=task,check_type=scheduled_task,host=ryzen,observer=ryzen,service=grafana-recovery age_seconds=100000i,code=2i,reason="overdue",source_timestamp=1789411726i <TS>
service_health,host=ryzen,observer=ryzen,service=networking-backup age_seconds=120i,impact_code=0i,reason="task:result_2147942402",source_timestamp=1789511606i,state_code=2i <TS>
service_check,check=task,check_type=scheduled_task,host=ryzen,observer=ryzen,service=networking-backup age_seconds=120i,code=2i,reason="result_2147942402",source_timestamp=1789511606i <TS>
service_health,host=ryzen,observer=ryzen,service=modem-poll impact_code=0i,reason="task:disabled_as_expected",state_code=4i <TS>
service_check,check=task,check_type=scheduled_task,host=ryzen,observer=ryzen,service=modem-poll code=4i,reason="disabled_as_expected" <TS>
service_health,host=ryzen,observer=ryzen,service=missing-task impact_code=0i,reason="task:task_missing",state_code=3i <TS>
service_check,check=task,check_type=scheduled_task,host=ryzen,observer=ryzen,service=missing-task code=3i,reason="task_missing" <TS>
service_health,host=ryzen,observer=ryzen,service=missing-service impact_code=0i,reason="service:service_missing",state_code=3i <TS>
service_check,check=service,check_type=windows_service,host=ryzen,observer=ryzen,service=missing-service code=3i,reason="service_missing" <TS>
service_health,host=ryzen,observer=ryzen,service=w32time age_seconds=0i,impact_code=0i,reason="service:running",source_timestamp=1789511726i,state_code=0i <TS>
service_check,check=service,check_type=windows_service,host=ryzen,observer=ryzen,service=w32time age_seconds=0i,code=0i,reason="running",source_timestamp=1789511726i <TS>
service_health,host=ryzen,observer=ryzen,service=docker-desktop-service impact_code=0i,reason="service:service_stopped",state_code=2i <TS>
service_check,check=service,check_type=windows_service,host=ryzen,observer=ryzen,service=docker-desktop-service code=2i,reason="service_stopped" <TS>
service_health,host=ryzen,observer=ryzen,service=closed-port impact_code=0i,reason="get:unreachable:WebException",state_code=2i <TS>
service_check,check=get,check_type=http,host=ryzen,observer=ryzen,service=closed-port code=2i,reason="unreachable:WebException" <TS>
service_health,host=ryzen,observer=ryzen,service=ha-remote impact_code=0i,reason="api:http_302",state_code=2i <TS>
service_check,check=api,check_type=http,host=ryzen,observer=ryzen,service=ha-remote code=2i,reason="http_302" <TS>
service_health,host=ryzen,observer=ryzen,service=soft-consumer age_seconds=0i,impact_code=1i,reason="service:running|impact:closed-port:degraded",source_timestamp=1789511726i,state_code=0i <TS>
service_check,check=service,check_type=windows_service,host=ryzen,observer=ryzen,service=soft-consumer age_seconds=0i,code=0i,reason="running",source_timestamp=1789511726i <TS>
service_health,host=ryzen,observer=ryzen,service=hard-consumer age_seconds=0i,impact_code=2i,reason="service:running|impact:grafana-recovery:failed",source_timestamp=1789511726i,state_code=0i <TS>
service_check,check=service,check_type=windows_service,host=ryzen,observer=ryzen,service=hard-consumer age_seconds=0i,code=0i,reason="running",source_timestamp=1789511726i <TS>
service_dependency,dependency_type=hard,host=ryzen,observer=ryzen,service=docker,upstream=os declared=1i,grace_seconds=0i,propagated_code=0i,upstream_effective_code=0i,upstream_state_code=0i <TS>
service_dependency,dependency_type=hard,host=ryzen,observer=ryzen,service=influxdb,upstream=docker declared=1i,grace_seconds=0i,propagated_code=0i,upstream_effective_code=3i,upstream_state_code=3i <TS>
service_dependency,dependency_type=soft,host=ryzen,observer=ryzen,service=grafana,upstream=influxdb declared=1i,grace_seconds=300i,propagated_code=0i,upstream_effective_code=0i,upstream_state_code=0i <TS>
service_dependency,dependency_type=soft,host=ryzen,observer=ryzen,service=grafana,upstream=lan declared=1i,grace_seconds=0i,propagated_code=0i,upstream_effective_code=3i,upstream_state_code=3i <TS>
service_dependency,dependency_type=hard,host=ryzen,observer=ryzen,service=mosquitto,upstream=docker declared=1i,grace_seconds=0i,propagated_code=0i,upstream_effective_code=3i,upstream_state_code=3i <TS>
service_dependency,dependency_type=hard,host=ryzen,observer=ryzen,service=iot-telegraf,upstream=mosquitto declared=1i,grace_seconds=0i,propagated_code=0i,upstream_effective_code=0i,upstream_state_code=0i <TS>
service_dependency,dependency_type=hard,host=ryzen,observer=ryzen,service=iot-telegraf,upstream=influxdb declared=1i,grace_seconds=0i,propagated_code=0i,upstream_effective_code=0i,upstream_state_code=0i <TS>
service_dependency,dependency_type=batch,host=ryzen,observer=ryzen,service=iot-recovery,upstream=influxdb declared=1i,grace_seconds=0i,propagated_code=0i,upstream_effective_code=0i,upstream_state_code=0i <TS>
service_dependency,dependency_type=soft,host=ryzen,observer=ryzen,service=soft-consumer,upstream=closed-port declared=1i,grace_seconds=300i,propagated_code=1i,upstream_effective_code=2i,upstream_state_code=2i <TS>
service_dependency,dependency_type=hard,host=ryzen,observer=ryzen,service=hard-consumer,upstream=grafana-recovery declared=1i,grace_seconds=0i,propagated_code=2i,upstream_effective_code=2i,upstream_state_code=2i <TS>
service_health,host=ryzen,observer=ryzen,service=health-evaluator age_seconds=0i,impact_code=0i,reason="ok;services=19;unknown=5;duration_ms=<N>;unprobed_checks=6",source_timestamp=1789511726i,state_code=0i <TS>
