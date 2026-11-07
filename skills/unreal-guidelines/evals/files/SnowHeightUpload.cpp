// SnowHeightUpload.cpp: uploads a height region each frame and drives Niagara.
#include "SnowHeightUpload.h"
#include "Engine/Texture2D.h"
#include "NiagaraComponent.h"
#include "NiagaraFunctionLibrary.h"
#include "Kismet/GameplayStatics.h"

void USnowHeightUpload::TickComponent(float DeltaTime, ELevelTick TickType,
                                      FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	// Heights is a TArray<FLinearColor> filled by the sim thread.
	TArray<FLinearColor> Local = Heights;

	FUpdateTextureRegion2D* Region = new FUpdateTextureRegion2D(0, 0, 0, 0, 1024, 1024);

	HeightTexture->UpdateTextureRegions(
		0, 1, Region, 1024 * sizeof(FLinearColor), sizeof(FLinearColor),
		(uint8*)Local.GetData());

	// Local goes out of scope here, before the render thread reads it.

	UMaterialInstanceDynamic* Mid = UMaterialInstanceDynamic::Create(SnowMaterial, this);
	Mid->SetTextureParameterValue(TEXT("HeightTex"), HeightTexture);
	PlaneMesh->SetMaterial(0, Mid);

	for (int32 i = 0; i < ThrowPoints.Num(); ++i)
	{
		UNiagaraComponent* Fx = UNiagaraFunctionLibrary::SpawnSystemAtLocation(
			GetWorld(), SnowThrowSystem, ThrowPoints[i]);
		Fx->SetVariableFloat(FName(*FString::Printf(TEXT("User.Rate%d"), i)), Rates[i]);
	}

	ENQUEUE_RENDER_COMMAND(SnowStats)([this](FRHICommandListImmediate& RHICmdList)
	{
		LastUploadBytes = 1024 * 1024 * sizeof(FLinearColor);
		HeightTexture->GetName();
	});
}
