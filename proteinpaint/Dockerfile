FROM ghcr.io/stjude/ppserver:2.214.0-b33a2fad7@sha256:4242772b10e43839f340f7120809eea9f4dbbf2d665ac250f06ba44b908602b6
USER root
WORKDIR /home/root/pp/app/active
RUN npm pkg set type=module && npm install --save-exact @sjcrh/proteinpaint-server@2.216.0 @sjcrh/proteinpaint-shared@2.216.0
COPY scripts/patch_proteinpaint.mjs /tmp/patch_proteinpaint.mjs
RUN node /tmp/patch_proteinpaint.mjs node_modules/@sjcrh/proteinpaint-server
COPY proteinpaint/serverconfig.json ./serverconfig.json
COPY proteinpaint/genome.mjs ./genome/synthetic.mjs
COPY proteinpaint/dataset.mjs ./dataset/synthetic.mjs
COPY generated /home/root/pp/tp
COPY synthetic/generate_assays.py /tmp/generate_assays.py
COPY synthetic/embedding.py /tmp/embedding.py
RUN apt-get update && apt-get install -y --no-install-recommends tabix && rm -rf /var/lib/apt/lists/* && /opt/venv/bin/python /tmp/generate_assays.py
RUN bcftools view -Ob -o /home/root/pp/tp/variants.bcf.gz /home/root/pp/tp/variants.vcf && bcftools index /home/root/pp/tp/variants.bcf.gz
