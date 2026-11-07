// SnowHeightUpload.h
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "SnowHeightUpload.generated.h"

UCLASS()
class USnowHeightUpload : public UActorComponent
{
	GENERATED_BODY()

public:
	virtual void TickComponent(float DeltaTime, ELevelTick TickType,
	                           FActorComponentTickFunction* ThisTickFunction) override;

	// Written by the sim thread without a lock.
	TArray<FLinearColor> Heights;

	UTexture2D* HeightTexture;      // format PF_A32B32G32R32F, 1024 x 1024
	UMaterialInterface* SnowMaterial;
	UStaticMeshComponent* PlaneMesh;
	UNiagaraSystem* SnowThrowSystem;

	TArray<FVector> ThrowPoints;
	TArray<float> Rates;
	uint64 LastUploadBytes;
};
