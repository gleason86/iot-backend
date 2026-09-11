FROM threadripper-validation
WORKDIR /iot
COPY roles roles
COPY playbooks playbooks
COPY scripts scripts
COPY tests tests
CMD ["bash", "tests/validate.sh"]
