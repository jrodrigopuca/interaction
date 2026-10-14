FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY scripts ./scripts
COPY packages/utils/package.json packages/utils/
COPY packages/core/package.json packages/core/
COPY packages/api/package.json packages/api/
RUN npm ci
COPY packages ./packages
RUN npm run build

FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/package.json /app/package-lock.json ./
COPY --from=build /app/packages/utils/package.json packages/utils/
COPY --from=build /app/packages/core/package.json packages/core/
COPY --from=build /app/packages/api/package.json packages/api/
RUN npm ci --omit=dev
COPY --from=build /app/packages/utils/dist packages/utils/dist
COPY --from=build /app/packages/core/dist packages/core/dist
COPY --from=build /app/packages/api/dist packages/api/dist
EXPOSE 3000
CMD ["npm", "-w", "@acme/api", "start"]
