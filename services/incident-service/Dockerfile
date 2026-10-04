FROM eclipse-temurin:17-jdk-jammy AS build

WORKDIR /workspace
COPY .mvn/ .mvn/
COPY mvnw pom.xml ./
RUN sed -i 's/\r$//' mvnw && chmod +x mvnw && ./mvnw -B -ntp dependency:go-offline

COPY src/ src/
RUN ./mvnw -B -ntp package -DskipTests

FROM eclipse-temurin:17-jre-jammy AS runtime

RUN useradd --system --uid 10001 --create-home aegis
WORKDIR /app
COPY --from=build --chown=aegis:aegis /workspace/target/incident-service.jar app.jar

USER aegis
ENV SERVER_PORT=8080
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
