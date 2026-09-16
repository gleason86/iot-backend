FROM threadripper-validation
WORKDIR /iot
COPY roles roles
COPY playbooks playbooks
COPY scripts scripts
COPY tools tools
COPY tests tests
CMD ["bash", "tests/validate.sh"]
