// SnowSledActor.h
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "EngineUtils.h"
#include "SnowSledActor.generated.h"

UCLASS()
class ASnowSledActor : public AActor
{
	GENERATED_BODY()

public:
	ASnowSledActor();
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaTime) override;

	UPROPERTY()
	UStaticMeshComponent* Body;

	// Other sleds and a helper actor.
	TArray<ASnowSledActor*> Others;
	AActor* TrailHelper;

	FCriticalSection ThrustLock;
	FVector PendingThrust;
	bool Boosting;
};
